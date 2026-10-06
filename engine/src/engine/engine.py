"""The Core Asynchronous Execution Engine (Breadth-First Search)."""

import asyncio
import ipaddress
import json
import logging
import sys
from typing import Any

from engine.operations.network import resolve_target
from engine.probes.http import check_http_routing
from engine.probes.tcp import check_tcp_and_tls
from engine.schemas.engine import IpState
from engine.utils.rate_limit import AsyncTokenBucket

logger = logging.getLogger(__name__)

# Track seen combinations to avoid duplicate probes
seen_tcp = set()
seen_http = set()

# Global to handle cancellation gracefully
is_cancelled = False
cancel_event = None
engine_loop: asyncio.AbstractEventLoop | None = None

async def scanner_routine(routine_id: str, queue: asyncio.Queue, limiter: AsyncTokenBucket):
    """
    Asynchronous routine that pulls tasks from the queue and executes them.
    """
    while not is_cancelled:
        try:
            task = await queue.get()
        except asyncio.CancelledError:
            break
            
        try:

            target = task.target
            ports = task.ports
            
            # Normalize domain to ip
            ip_address, host_header, is_domain = await resolve_target(target)
            if not ip_address:
                logger.error(f"[Routine {routine_id}] Error: Could not resolve domain {target}")
                continue

            state_key = ip_address
            
            # --- Depth and Scope Tracking ---
            parent_ip = task.context.parent_ip
            current_depth = task.context.depth
            
            if parent_ip is None:
                # Seed task
                parent_ip = ip_address
            elif ip_address != parent_ip:
                current_depth += 1
                
            max_depth = task.context.flags.out_of_scope_depth
            if current_depth > max_depth:
                logger.info(f"[Routine {routine_id}] Skipping {target} (IP: {state_key}) - Exceeds max depth ({current_depth} > {max_depth})")
                continue

            logger.info(f"[Routine {routine_id}] Processing {target} (IP: {state_key}) on ports {ports} (Depth {current_depth})")
            
            # Initialize localized IpState for this task
            local_state = IpState()
            if is_domain:
                local_state.metadata.resolved_from = target
            if task.context.discovered_from:
                local_state.metadata.discovered_from.append(task.context.discovered_from)
                
            has_updates = False
            # Execute the probes for each port
            for port in ports:
                tcp_cache_key = f"{state_key}:{port}"
                host_header_key = host_header or state_key
                http_cache_key = f"{state_key}:{port}:{host_header_key}"
                
                check_vhosts = task.context.flags.check_virtual_hosts
                
                skip_tcp = tcp_cache_key in seen_tcp
                skip_http = http_cache_key in seen_http
                
                if not check_vhosts and skip_tcp:
                    skip_http = True
                    
                if skip_tcp and skip_http:
                    continue
                    
                from engine.schemas.engine import PortState
                local_state.ports[port] = PortState()
                
                if not skip_tcp:
                    seen_tcp.add(tcp_cache_key)
                    has_updates = True
                    
                    await limiter.acquire()
                    tcp_result = await check_tcp_and_tls(state_key, port, server_hostname=host_header)
                    
                    local_state.ports[port] = tcp_result
                    
                    # If we found SANs, and recursive checking is enabled in the flags
                    if tcp_result.tls_certificate and task.context.flags.recursive_san_check:
                        for san in tcp_result.tls_certificate.domains_discovered_sans:
                            if "*" not in san:  # Avoid queuing wildcard domains directly
                                try:
                                    ipaddress.IPv4Address(san)
                                    discovered_from = state_key
                                except ValueError:
                                    discovered_from = None
                                    
                                from engine.schemas.engine import EngineTask, TaskContext
                                await queue.put(EngineTask(
                                    target=san, 
                                    ports=[port],
                                    context=TaskContext(
                                        flags=task.context.flags,
                                        discovered_from=discovered_from,
                                        parent_ip=ip_address,
                                        depth=current_depth
                                    )
                                ))
                
                if not skip_http and task.context.flags.check_http:
                    seen_http.add(http_cache_key)
                    has_updates = True
                    
                    await limiter.acquire()
                    http_result = await check_http_routing(state_key, port, host_header=host_header, flags=task.context.flags)
                    local_state.ports[port].http_routing_checks[host_header_key] = http_result
                    
                    if http_result.redirects_to_url:
                        from engine.schemas.engine import EngineTask, TaskContext
                        try:
                            redirect_task = EngineTask.from_redirect_url(
                                url=http_result.redirects_to_url,
                                context=TaskContext(
                                    flags=task.context.flags,
                                    discovered_from=state_key,
                                    parent_ip=ip_address,
                                    depth=current_depth
                                )
                            )
                            await queue.put(redirect_task)
                        except Exception as e:
                            logger.warning(f"[Routine {routine_id}] Error parsing redirect URL {http_result.redirects_to_url}: {e}")
            
            # Emit NDJSON delta if we did any work
            if has_updates:
                import dataclasses
                delta = {state_key: dataclasses.asdict(local_state)}
                sys.stdout.write(json.dumps(delta) + "\n")
                sys.stdout.flush()
                
        except asyncio.CancelledError:
            break
        except Exception as e:
            import traceback
            logger.error(f"[Routine {routine_id}] Unhandled exception processing task {getattr(task, 'target', 'unknown')}: {e}")
            logger.error(traceback.format_exc())
        finally:
            queue.task_done()

async def async_main(tasks_data: list[dict[str, Any]], workers_count: int = 100):
    """
    Initializes the BFS queue, spawns the routines, and blocks until finished.
    """
    global cancel_event, engine_loop
    cancel_event = asyncio.Event()
    engine_loop = asyncio.get_running_loop()
    
    queue = asyncio.Queue()
    
    # Seeding queue with JSON input
    from engine.schemas.engine import EngineTask, TaskContext, TaskFlags
    first_task = None
    for task_dict in tasks_data:
        flags = TaskFlags(**task_dict.get("flags", {}))
        task = EngineTask(
            target=task_dict["target"],
            ports=task_dict["ports"],
            context=TaskContext(
                flags=flags,
                discovered_from=task_dict.get("discovered_from"),
                parent_ip=task_dict.get("parent_ip"),
                depth=task_dict.get("depth", 0)
            )
        )
        if first_task is None:
            first_task = task
        await queue.put(task)
        
    # Get rate from the first task's parsed flags to avoid primitive obsession
    rate_limit = 50.0
    if first_task and hasattr(first_task.context.flags, 'rate'):
        rate_limit = first_task.context.flags.rate
    
    limiter = AsyncTokenBucket(rate_limit)
        
    workers = []
    
    for i in range(workers_count):
        worker_task = asyncio.create_task(scanner_routine(f"W-{i}", queue, limiter))
        workers.append(worker_task)
        
    # Wait until queue is empty or cancelled
    queue_task = asyncio.create_task(queue.join())
    cancel_task = asyncio.create_task(cancel_event.wait())
    
    done, pending = await asyncio.wait(
        [queue_task, cancel_task],
        return_when=asyncio.FIRST_COMPLETED
    )
    for p in pending:
        p.cancel()
    
    # Cancel the workers
    for w in workers:
        w.cancel()
        
    await asyncio.gather(*workers, return_exceptions=True)

def cancel_engine():
    """Request cancellation. Safe to call from a signal handler: the loop may be
    blocked in select() (e.g. a worker sleeping on --delay), so we must wake it
    through call_soon_threadsafe instead of setting the Event directly."""
    global is_cancelled
    is_cancelled = True
    if cancel_event is not None and engine_loop is not None and not engine_loop.is_closed():
        engine_loop.call_soon_threadsafe(cancel_event.set)

def run_engine(tasks_data: list[dict[str, Any]], workers_count: int = 100):
    """
    The synchronous boundary that the CLI calls.
    It triggers the asyncio event loop.
    """
    global seen_tcp, seen_http, is_cancelled
    seen_tcp.clear()
    seen_http.clear()
    is_cancelled = False
    
    logger.info(f"[*] Starting Asyncio Breadth-First Scanner Engine with {workers_count} concurrent routines...")
    asyncio.run(async_main(tasks_data, workers_count=workers_count))
