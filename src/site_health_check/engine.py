"""The Core Asynchronous Execution Engine (Breadth-First Search)."""

import asyncio
from typing import Any, Dict, List

from site_health_check.schema import IpState, PortState, TlsCertificate, HttpRoutingCheck
from site_health_check.probes.tcp import check_tcp_and_tls
from site_health_check.probes.http import check_http_routing

# The master state dictionary: IP (str) -> IpState
master_state: Dict[str, IpState] = {}
seen_targets = set()

async def worker(worker_id: str, queue: asyncio.Queue):
    """
    Asynchronous worker that pulls tasks from the queue and executes them.
    """
    while True:
        task = await queue.get()
        
        # Example Task Structure from CLI:
        # task = {"target": "143.106.10.50", "ports": [443], "flags": {...}}
        
        target = task["target"]
        ports = task["ports"]
        
        # Basic caching to prevent infinite loops (especially important when checking SANs)
        cache_key = f"{target}:{ports}"
        if cache_key in seen_targets:
            queue.task_done()
            continue
            
        seen_targets.add(cache_key)
        print(f"[Worker {worker_id}] Processing {target} on ports {ports}")
        
        # Initialize the state if this IP is totally new
        if target not in master_state:
            master_state[target] = IpState()
            
        # Execute the probes for each port
        for port in ports:
            # 1. The TCP Pass (Sockets)
            # You will implement the real socket logic in probes/tcp.py
            tcp_result = await check_tcp_and_tls(target, port)
            
            # Update State
            master_state[target].ports[port] = PortState(
                tcp_status=tcp_result.get("tcp_status", "closed"),
                tcp_latency_ms=tcp_result.get("tcp_latency_ms")
            )
            
            # If TLS is valid, populate it and check for SANs
            if tcp_result.get("tls_certificate"):
                cert_data = tcp_result["tls_certificate"]
                tls_obj = TlsCertificate(
                    valid=cert_data.get("valid", False),
                    domains_discovered_sans=cert_data.get("domains_discovered_sans", [])
                )
                master_state[target].ports[port].tls_certificate = tls_obj
                
                # --- THE BFS QUEUE MAGIC ---
                # If we found SANs, and recursive checking is enabled in the flags, 
                # we push them to the BACK of the queue!
                # if task.get("flags", {}).get("recursive_san_check"):
                #     for san in tls_obj.domains_discovered_sans:
                #         await queue.put({
                #             "target": san, 
                #             "ports": [port],
                #             "flags": task.get("flags", {})
                #         })
            
            # 2. The HTTP Pass (aiohttp)
            # You will implement this in probes/http.py
            # http_result = await check_http_routing(target, port, host_header=target)
            
        queue.task_done()

async def async_main(payload: List[Dict[str, Any]]):
    """
    Initializes the BFS queue, spawns the workers, and blocks until finished.
    """
    queue = asyncio.Queue()
    
    # 1. Seed the queue with the JSON payload from the CLI
    for task in payload:
        await queue.put(task)
        
    # 2. Spin up the workers. 
    # Hardcoded to 1 for now to prevent rate-limiting while you build the sockets!
    # In production, you would increase this to 50-100.
    worker_limit = 1
    workers = []
    
    for i in range(worker_limit):
        worker_task = asyncio.create_task(worker(f"W-{i}", queue))
        workers.append(worker_task)
        
    # 3. Wait until the queue is completely empty
    await queue.join()
    
    # 4. Cancel the workers
    for w in workers:
        w.cancel()
        
    # Wait for the cancellations to finish
    await asyncio.gather(*workers, return_exceptions=True)
    
    return master_state

def run_engine(payload: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    The synchronous boundary that the CLI calls.
    It triggers the asyncio event loop and returns the final serialized dictionary.
    """
    print("\n[*] Starting Asyncio Breadth-First Engine...")
    
    # Run the async loop
    final_state_objects = asyncio.run(async_main(payload))
    
    # Serialize the dataclasses to raw dictionaries for JSON dumping
    # Need to manually call asdict or similar since IpState doesn't have it explicitly bound
    # We'll use a hack or proper method. Wait, dataclasses.asdict() works perfectly.
    import dataclasses
    serialized_results = {}
    for ip, state_obj in final_state_objects.items():
        serialized_results[ip] = dataclasses.asdict(state_obj)
        
    return serialized_results
