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
from engine.parsing import ScopeValidator

logger = logging.getLogger(__name__)

# Track seen combinations to avoid duplicate probes
seen_tcp = {}
seen_http = set()

# Global to handle cancellation gracefully
is_cancelled = False
cancel_event = None
engine_loop: asyncio.AbstractEventLoop | None = None
global_output_format = "json"
global_outfile_path = None
global_outfile_handle = None

async def scanner_routine(routine_id: str, queue: asyncio.Queue, limiter: AsyncTokenBucket, validator: ScopeValidator | None = None):
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
            
            parent_ip = task.context.parent_ip
            r_depth = task.context.redirect_depth
            s_depth = task.context.san_depth
            
            # --- Vhost Probing (DNS Bypass) ---
            if task.context.flags.force_vhost_origin:
                ip_address = parent_ip or target
                host_header = target
                is_domain = True
            else:
                ip_address, host_header, is_domain = await resolve_target(target)
                if not ip_address:
                    logger.error(f"[Routine {routine_id}] Error: Could not resolve domain {target}")
                    continue

            # --- Scope Validation ---
            if validator and not validator.is_in_scope(ip_address):
                if task.context.source_type == "redirect" and not task.context.flags.follow_redirects_out_of_scope:
                    logger.info(f"[Routine {routine_id}] Dropped {target} ({ip_address}) - Out of scope redirect")
                    continue
                if task.context.source_type == "san" and not task.context.flags.follow_sans_out_of_scope:
                    logger.info(f"[Routine {routine_id}] Dropped {target} ({ip_address}) - Out of scope SAN")
                    continue
                if task.context.source_type == "seed":
                    logger.info(f"[Routine {routine_id}] Dropped {target} ({ip_address}) - Out of scope seed")
                    continue
            
            # --- Depth Tracking ---
            if parent_ip is None:
                parent_ip = ip_address
            elif ip_address != parent_ip:
                if task.context.source_type == "redirect":
                    r_depth += 1
                elif task.context.source_type == "san":
                    s_depth += 1
                    
            if r_depth > task.context.flags.max_depth_redirects:
                logger.info(f"[Routine {routine_id}] Skipping {target} (IP: {ip_address}) - Exceeds max redirect depth")
                continue
                
            if s_depth > task.context.flags.max_depth_sans:
                logger.info(f"[Routine {routine_id}] Skipping {target} (IP: {ip_address}) - Exceeds max SAN depth")
                continue

            state_key = ip_address
            logger.info(f"[Routine {routine_id}] Processing {target} (IP: {state_key}) on ports {ports}")
            
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
                    seen_tcp[tcp_cache_key] = "open"  # placeholder to prevent duplicate probes
                    has_updates = True
                    
                    await limiter.acquire()
                    tcp_result = await check_tcp_and_tls(state_key, port, server_hostname=host_header)
                    
                    local_state.ports[port] = tcp_result
                    seen_tcp[tcp_cache_key] = tcp_result.tcp_status
                    
                    # If we found SANs, and recursive checking is enabled in the flags
                    if tcp_result.tls_certificate and task.context.flags.follow_sans:
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
                                        source_type="san",
                                        redirect_depth=r_depth,
                                        san_depth=s_depth
                                    )
                                ))
                else:
                    local_state.ports[port].tcp_status = seen_tcp.get(tcp_cache_key, "closed")
                
                if not skip_http and task.context.flags.check_http:
                    seen_http.add(http_cache_key)
                    has_updates = True
                    
                    await limiter.acquire()
                    http_result = await check_http_routing(state_key, port, host_header=host_header, flags=task.context.flags)
                    local_state.ports[port].http_routing_checks[host_header_key] = http_result
                    
                    if http_result.redirects_to_url and task.context.flags.follow_redirects:
                        from engine.schemas.engine import EngineTask, TaskContext
                        try:
                            redirect_task = EngineTask.from_redirect_url(
                                url=http_result.redirects_to_url,
                                context=TaskContext(
                                    flags=task.context.flags,
                                    discovered_from=state_key,
                                    parent_ip=ip_address,
                                    source_type="redirect",
                                    redirect_depth=r_depth,
                                    san_depth=s_depth
                                )
                            )
                            await queue.put(redirect_task)
                        except Exception as e:
                            logger.warning(f"[Routine {routine_id}] Error parsing redirect URL {http_result.redirects_to_url}: {e}")
            
            # Emit NDJSON delta if we did any work
            if has_updates:
                import dataclasses
                delta = {state_key: dataclasses.asdict(local_state)}
                json_str = json.dumps(delta)
                
                # Write to --outfile if specified (always JSON)
                if global_outfile_handle:
                    global_outfile_handle.write(json_str + "\n")
                    global_outfile_handle.flush()
                
                # Write to stdout based on format
                if global_output_format == "classic":
                    lines = []
                    for port, port_state in local_state.ports.items():
                        tcp = port_state.tcp_status.upper()
                        target_col = f"{state_key}:{port}"
                        if not port_state.http_routing_checks:
                            lines.append(f"{target_col:<22} {tcp:<6} {'NONE':<35} {'NONE':<9} {'NONE':<20} NONE")
                        else:
                            for host, http in port_state.http_routing_checks.items():
                                status = f"HTTP_{http.status_code}" if http.status_code else "NONE"
                                server = (http.server_header or "NONE").replace(" ", "_")
                                redir = http.redirects_to_url or "NONE"
                                lines.append(f"{target_col:<22} {tcp:<6} {host[:34]:<35} {status:<9} {server[:19]:<20} {redir}")
                    if lines:
                        sys.stdout.write("\n".join(lines) + "\n")
                        sys.stdout.flush()
                else:
                    # Default JSON
                    sys.stdout.write(json_str + "\n")
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
                source_type="seed",
                redirect_depth=0,
                san_depth=0
            )
        )
        if first_task is None:
            first_task = task
        await queue.put(task)
        
    validator = None
    if first_task:
        validator = ScopeValidator(
            whitelist=first_task.context.flags.whitelist,
            blacklist=first_task.context.flags.blacklist
        )
        
    # Get rate from the first task's parsed flags to avoid primitive obsession
    rate_limit = 50.0
    if first_task and hasattr(first_task.context.flags, 'rate'):
        rate_limit = first_task.context.flags.rate
    
    limiter = AsyncTokenBucket(rate_limit)
        
    workers = []
    
    for i in range(workers_count):
        worker_task = asyncio.create_task(scanner_routine(f"W-{i}", queue, limiter, validator))
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

def run_engine(tasks_data: list[dict[str, Any]], workers_count: int = 100, output_format: str = "json", outfile: str | None = None):
    """
    The synchronous boundary that the CLI calls.
    It triggers the asyncio event loop.
    """
    global seen_tcp, seen_http, is_cancelled, global_output_format, global_outfile_path, global_outfile_handle
    seen_tcp.clear()
    seen_http.clear()
    is_cancelled = False
    
    global_output_format = output_format
    global_outfile_path = outfile
    
    if outfile:
        global_outfile_handle = open(outfile, "a", encoding="utf-8")
    else:
        global_outfile_handle = None
        
    if output_format == "classic":
        sys.stdout.write(f"{'TARGET':<22} {'TCP':<6} {'HOST_HEADER':<35} {'HTTP':<9} {'SERVER':<20} REDIRECT\n")
        sys.stdout.flush()
    
    try:
        logger.info(f"[*] Starting Asyncio Breadth-First Scanner Engine with {workers_count} concurrent routines...")
        asyncio.run(async_main(tasks_data, workers_count=workers_count))
    finally:
        if global_outfile_handle:
            global_outfile_handle.close()
