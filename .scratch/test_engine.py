import asyncio
import dataclasses
import json

# We need to mock the probes to avoid real network calls, OR we can just use the real network calls 
# since it's a real IP and domain. But wait, I shouldn't spam the openstack cloud.
# Instead, I'll mock `resolve_target`, `check_tcp_and_tls`, and `check_http_routing`.
import engine.engine as engine_module
from engine.engine import async_main


async def mock_resolve_target(target):
    if target == "143.106.2.17":
        return "143.106.2.17", None, False
    return "143.106.2.17", target, True

engine_module.resolve_target = mock_resolve_target

from engine.schemas.engine import HttpRoutingCheck, PortState, TlsCertificate


async def mock_check_tcp_and_tls(ip, port, server_hostname):
    cert = TlsCertificate(
        valid=True,
        issuer="test",
        domains_discovered_sans=["atacama.unicamp.br", "monitor.redesemfio.unicamp.br"],
        expires_in_days=5,
        protocol_version="TLSv1.3"
    )
    return PortState(
        tcp_status="open",
        tcp_latency_ms=35,
        tls_certificate=cert
    )

engine_module.check_tcp_and_tls = mock_check_tcp_and_tls

async def mock_check_http_routing(ip, port, host_header, flags):
    return HttpRoutingCheck(
        status_code=200,
        http_latency_ms=129,
        server_header="test"
    )

engine_module.check_http_routing = mock_check_http_routing

async def run():
    payload = [{
        "target": "143.106.2.17",
        "ports": [443],
        "flags": {
            "recursive_san_check": True,
            "check_virtual_hosts": True
        }
    }]
    
    results = await async_main(payload, workers_count=1)
    
    output = {}
    for ip, state in results.items():
        output[ip] = dataclasses.asdict(state)
        
    print(json.dumps(output, indent=2))

if __name__ == "__main__":
    asyncio.run(run())
