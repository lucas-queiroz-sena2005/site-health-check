"""HTTP routing and validation probes."""
import asyncio
import ssl
import time
from typing import Any

import aiohttp
import aiohttp.abc

from engine.schemas.engine import HttpRoutingCheck, TaskFlags

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

_SSL_CONTEXT = ssl.create_default_context()
_SSL_CONTEXT.check_hostname = False
_SSL_CONTEXT.verify_mode = ssl.CERT_NONE

async def check_http_routing(ip: str, port: int, host_header: str | None, flags: TaskFlags) -> HttpRoutingCheck:
    """
    Validates HTTP payloads for a given Virtual Host (domain) on a specific IP.
    """
    result = HttpRoutingCheck(path_checked="/")
    
    domain_in_url = host_header if host_header else ip
    scheme = "http" if port == 80 else "https"
    url = f"{scheme}://{domain_in_url}:{port}/"
    
    resolver = SingleIPResolver(target_ip=ip)
    
    connector = aiohttp.TCPConnector(resolver=resolver, ssl=_SSL_CONTEXT)
    
    headers = {}
    if flags.user_agent:
        headers["User-Agent"] = flags.user_agent
    else:
        headers["User-Agent"] = "site-health-check/1.0"
    
    try:
        async with aiohttp.ClientSession(connector=connector, headers=headers) as session:
            start_time = time.perf_counter()
            async with session.get(url, timeout=flags.timeout_seconds, allow_redirects=False) as response:
                result.status_code = response.status
                result.http_latency_ms = int((time.perf_counter() - start_time) * 1000)
                result.server_header = response.headers.get("Server")
                
                if 300 <= response.status < 400:
                    location = response.headers.get("Location")
                    if location:
                        import yarl
                        result.redirects_to_url = str(response.url.join(yarl.URL(location)))
                            
    except asyncio.TimeoutError:
        result.notes = "HTTP Timeout"
    except Exception as e:
        result.notes = f"HTTP Request Failed: {type(e).__name__} - {e}"
        
    return result

