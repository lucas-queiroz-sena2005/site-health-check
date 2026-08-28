"""The Core Asynchronous Execution Engine (Breadth-First Search)."""

import asyncio
import aiohttp
from typing import Any

import ipaddress
from site_health_check.operations.network import resolve_target
from site_health_check.probes.tcp import check_tcp_and_tls
from site_health_check.probes.http import check_http_routing
from site_health_check.schemas.engine import IpState

# The master state dictionary: IP (str) -> IpState
master_state: dict[str, IpState] = {}
seen_tcp = set()
seen_http = set()

async def worker(worker_id: str, queue: asyncio.Queue):
    """
    Asynchronous worker that pulls tasks from the queue and executes them.
    """
    while True:
        task = await queue.get()
        
        try:
            delay = task.get("flags", {}).get("worker_delay", 0.0)
            if delay > 0:
                await asyncio.sleep(delay)

            target = task["target"]
            ports = task["ports"]
            
            # Normalize domain to ip
            ip_address, host_header, is_domain = await resolve_target(target)
            if not ip_address:
                print(f"[Worker {worker_id}] Error: Could not resolve domain {target}")
                continue

            state_key = ip_address
            
            # --- Depth and Scope Tracking ---
            parent_ip = task.get("parent_ip")
            current_depth = task.get("depth", 0)
            
            if parent_ip is None:
                # Seed task
                parent_ip = ip_address
            elif ip_address != parent_ip:
                current_depth += 1
                
            max_depth = task.get("flags", {}).get("out_of_scope_depth", 0)
            if current_depth > max_depth:
                print(f"[Worker {worker_id}] Skipping {target} (IP: {state_key}) - Exceeds max depth ({current_depth} > {max_depth})")
                continue

            print(f"[Worker {worker_id}] Processing {target} (IP: {state_key}) on ports {ports} (Depth {current_depth})")
            
            # Initialize if IP is new
            if state_key not in master_state:
                master_state[state_key] = IpState()
                if is_domain:
                    master_state[state_key].metadata.resolved_from = target
                if task.get("discovered_from"):
                    master_state[state_key].metadata.discovered_from.append(task.get("discovered_from"))
                
            # Execute the probes for each port
            for port in ports:
                tcp_cache_key = f"{state_key}:{port}"
                host_header_key = host_header or state_key
                http_cache_key = f"{state_key}:{port}:{host_header_key}"
                
                check_vhosts = task.get("flags", {}).get("check_virtual_hosts", True)
                
                skip_tcp = tcp_cache_key in seen_tcp
                skip_http = http_cache_key in seen_http
                
                # If virtual host checking is OFF, and we've already done TCP for this IP/port, skip HTTP entirely.
                if not check_vhosts and skip_tcp:
                    skip_http = True
                    
                if skip_tcp and skip_http:
                    continue
                    
                if not skip_tcp:
                    seen_tcp.add(tcp_cache_key)
                    
                    # Pre-initialize PortState synchronously to prevent KeyErrors
                    # from other workers doing concurrent HTTP checks on the same IP/Port
                    if port not in master_state[state_key].ports:
                        from site_health_check.schemas.engine import PortState
                        master_state[state_key].ports[port] = PortState()
                        
                    tcp_result = await check_tcp_and_tls(state_key, port, server_hostname=host_header)
                    
                    # Preserve any HTTP routing checks added by concurrent workers while we were awaiting
                    existing_checks = master_state[state_key].ports[port].http_routing_checks
                    tcp_result.http_routing_checks.update(existing_checks)
                    master_state[state_key].ports[port] = tcp_result
                    
                    # If we found SANs, and recursive checking is enabled in the flags, 
                    # we push them to the BACK of the queue!
                    if tcp_result.tls_certificate and task.get("flags", {}).get("recursive_san_check"):
                        for san in tcp_result.tls_certificate.domains_discovered_sans:
                            if "*" not in san:  # Avoid queuing wildcard domains directly
                                try:
                                    ipaddress.IPv4Address(san)
                                    discovered_from = state_key
                                except ValueError:
                                    discovered_from = None
                                    
                                await queue.put({
                                    "target": san, 
                                    "ports": [port],
                                    "flags": task.get("flags", {}),
                                    "discovered_from": discovered_from,
                                    "parent_ip": ip_address,
                                    "depth": current_depth
                                })
                
                if not skip_http:
                    seen_http.add(http_cache_key)
                    # 2. The HTTP Pass (aiohttp)
                    from site_health_check.schemas.engine import TaskFlags
                    flags_obj = TaskFlags(**task.get("flags", {}))
                    http_result = await check_http_routing(state_key, port, host_header=host_header, flags=flags_obj)
                    master_state[state_key].ports[port].http_routing_checks[host_header_key] = http_result
        
        except Exception as e:
            import traceback
            print(f"[Worker {worker_id}] Unhandled exception processing task {task.get('target', 'unknown')}: {e}")
            traceback.print_exc()
        finally:
            queue.task_done()

async def async_main(payload: list[dict[str, Any]], workers_count: int = 100):
    """
    Initializes the BFS queue, spawns the workers, and blocks until finished.
    """
    queue = asyncio.Queue()
    
    # Seeding queue with JSON payload
    for task in payload:
        await queue.put(task)
        
    workers = []
    
    for i in range(workers_count):
        worker_task = asyncio.create_task(worker(f"W-{i}", queue))
        workers.append(worker_task)
        
    # Wait until queue is empty
    await queue.join()
    
    # Cancel the workers
    for w in workers:
        w.cancel()
        
    await asyncio.gather(*workers, return_exceptions=True)
    return master_state

def run_engine(payload: list[dict[str, Any]], workers_count: int = 100) -> dict[str, Any]:
    """
    The synchronous boundary that the CLI calls.
    It triggers the asyncio event loop and returns the final serialized dictionary.
    """
    global master_state, seen_tcp, seen_http
    master_state.clear()
    seen_tcp.clear()
    seen_http.clear()
    
    print(f"\n[*] Starting Asyncio Breadth-First Engine with {workers_count} workers...")
    final_state_objects = asyncio.run(async_main(payload, workers_count=workers_count))
    
    import dataclasses
    serialized_results = {}
    for ip, state_obj in final_state_objects.items():
        serialized_results[ip] = dataclasses.asdict(state_obj)
        
    return serialized_results
