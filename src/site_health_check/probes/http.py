"""HTTP routing and validation probes."""
import asyncio
import ssl
from typing import Any

import aiohttp
import aiohttp.abc

from site_health_check.catcher import validate_html
from site_health_check.schemas.engine import HttpRoutingCheck, TaskFlags

class SingleIPResolver(aiohttp.abc.AbstractResolver):
    """
    A custom DNS resolver that intercepts all requests and routes them 
    strictly to the provided target IP, bypassing real DNS resolution.
    """
    def __init__(self, target_ip: str):
        self.target_ip = target_ip

    async def resolve(self, host: str, port: int, family: int) -> list[dict[str, Any]]:
        return [{
            'hostname': host,
            'host': self.target_ip,
            'port': port,
            'family': family,
            'proto': 0,
            'flags': 0
        }]
        
    async def close(self):
        pass

async def check_http_routing(ip: str, port: int, host_header: str | None, flags: TaskFlags) -> HttpRoutingCheck:
    """
    Validates HTTP payloads for a given Virtual Host (domain) on a specific IP.
    """
    result = HttpRoutingCheck(path_checked="/")
    
    domain_in_url = host_header if host_header else ip
    scheme = "http" if port == 80 else "https"
    url = f"{scheme}://{domain_in_url}:{port}/"
    
    resolver = SingleIPResolver(target_ip=ip)
    
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    connector = aiohttp.TCPConnector(resolver=resolver, ssl=ssl_context)
    
    headers = {}
    if flags.spoof_user_agent:
        headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
    
    try:
        async with aiohttp.ClientSession(connector=connector, headers=headers) as session:
            async with session.get(url, timeout=flags.timeout_seconds) as response:
                result.status_code = response.status
                
                if flags.expected_strings or flags.undesired_strings:
                    body = await response.text()
                    passed, message = validate_html(
                        html_content=body,
                        expected_strings=flags.expected_strings,
                        undesired_strings=flags.undesired_strings,
                        require_all_expected=True,
                        reject_any_undesired=True
                    )
                    
                    if not passed:
                        result.notes = message
                            
    except asyncio.TimeoutError:
        result.notes = "HTTP Timeout"
    except Exception as e:
        result.notes = f"HTTP Request Failed: {type(e).__name__} - {e}"
        
    return result

