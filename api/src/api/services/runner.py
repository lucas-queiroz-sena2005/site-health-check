import asyncio
import json
import os
import signal
import sys
from datetime import datetime, timezone
from typing import Any

from fastapi.sse import ServerSentEvent
from sqlmodel import Session, select
from sqlalchemy.dialects.sqlite import insert

from api.database import engine as db_engine
from api.models import (
    ExecutionFlags,
    HostState,
    HttpRoutingCheck,
    PortState,
    ScanRun,
    ScanRunStatus,
    TlsCertificate,
)

def _upsert_delta_sync(run_id: str, ip: str, data: dict[str, Any]):
    """Sync function to upsert a single NDJSON delta into the DB using SQLite ON CONFLICT DO UPDATE"""
    with Session(db_engine) as session:
        # Upsert HostState
        metadata = data.get("metadata", {})
        stmt_host = insert(HostState).values(
            id=f"{run_id}_{ip}", # Deterministic ID is best, but we are using uuid4 default. Wait, we can let sqlite generate UUID or just use insert().on_conflict_do_update.
            scan_run_id=run_id,
            ip_address=ip,
            metadata_resolved_from=metadata.get("resolved_from"),
            metadata_discovered_from_json=metadata.get("discovered_from", []),
            subrun_id=metadata.get("subrun_id")
        ).on_conflict_do_update(
            index_elements=["scan_run_id", "ip_address"],
            set_={
                "metadata_resolved_from": metadata.get("resolved_from"),
                "metadata_discovered_from_json": metadata.get("discovered_from", []),
                "subrun_id": metadata.get("subrun_id")
            }
        ).returning(HostState.id)
        
        result_host = session.exec(stmt_host).first()
        host_id = result_host[0] if hasattr(result_host, "_mapping") or isinstance(result_host, tuple) else result_host

        ports = data.get("ports", {})
        for port_str, port_data in ports.items():
            port_num = int(port_str)
            stmt_port = insert(PortState).values(
                id=f"{host_id}_{port_num}",
                host_state_id=host_id,
                port_number=port_num,
                tcp_status=port_data.get("tcp_status", "closed"),
                tcp_latency_ms=port_data.get("tcp_latency_ms")
            ).on_conflict_do_update(
                index_elements=["host_state_id", "port_number"],
                set_={
                    "tcp_status": port_data.get("tcp_status", "closed"),
                    "tcp_latency_ms": port_data.get("tcp_latency_ms")
                }
            ).returning(PortState.id)
            
            result_port = session.exec(stmt_port).first()
            port_id = result_port[0] if hasattr(result_port, "_mapping") or isinstance(result_port, tuple) else result_port

            tls = port_data.get("tls_certificate")
            if tls:
                # We can just delete existing TLS and insert new for simplicity, 
                # or use a unique constraint. Let's assume one-to-one so we can just delete old ones.
                session.exec(TlsCertificate.__table__.delete().where(TlsCertificate.port_state_id == port_id))
                tls_cert = TlsCertificate(
                    port_state_id=port_id,
                    valid=tls.get("valid", False),
                    expires_in_days=tls.get("expires_in_days", 0),
                    issuer=tls.get("issuer"),
                    protocol_version=tls.get("protocol_version"),
                    domains_discovered_sans_json=tls.get("domains_discovered_sans", [])
                )
                session.add(tls_cert)

            routing = port_data.get("http_routing_checks", {})
            for domain, r_data in routing.items():
                stmt_route = insert(HttpRoutingCheck).values(
                    id=f"{port_id}_{domain}",
                    port_state_id=port_id,
                    domain=domain,
                    status_code=r_data.get("status_code"),
                    http_latency_ms=r_data.get("http_latency_ms"),
                    path_checked=r_data.get("path_checked", "/"),
                    redirects_to_url=r_data.get("redirects_to_url"),
                    server_header=r_data.get("server_header"),
                    notes=r_data.get("notes")
                ).on_conflict_do_update(
                    index_elements=["port_state_id", "domain"],
                    set_={
                        "status_code": r_data.get("status_code"),
                        "http_latency_ms": r_data.get("http_latency_ms"),
                        "path_checked": r_data.get("path_checked", "/"),
                        "redirects_to_url": r_data.get("redirects_to_url"),
                        "server_header": r_data.get("server_header"),
                        "notes": r_data.get("notes")
                    }
                )
                session.exec(stmt_route)
                
        session.commit()

async def _ingest_stdout(run_id: str, process: asyncio.subprocess.Process):
    if not process.stdout:
        return
        
    while True:
        line = await process.stdout.readline()
        if not line:
            break
            
        line_str = line.decode('utf-8').strip()
        if not line_str:
            continue
            
        try:
            payload = json.loads(line_str)
            # Check if this is the final summary line
            if "status" in payload:
                # The process might be done or aborted, we let the main loop handle the final state update.
                continue
                
            # Otherwise it's a delta
            for ip, data in payload.items():
                await asyncio.to_thread(_upsert_delta_sync, run_id, ip, data)
        except json.JSONDecodeError:
            pass

def _finalize_run(run_id: str, returncode: int):
    with Session(db_engine) as session:
        run = session.get(ScanRun, run_id)
        if not run:
            return
            
        run.finished_at = datetime.now(timezone.utc)
        
        if returncode == 130 or returncode == 143:
            run.status = ScanRunStatus.ABORTED
        elif returncode != 0:
            run.status = ScanRunStatus.FAILED
        else:
            run.status = ScanRunStatus.COMPLETED

        # Calculate metrics
        duration = 0.0
        if run.started_at and run.finished_at:
            started_at = run.started_at
            if started_at.tzinfo is None:
                started_at = started_at.replace(tzinfo=timezone.utc)
            duration = round((run.finished_at - started_at).total_seconds(), 2)
            
        # Anomalies
        anomalies = 0
        hosts = session.exec(select(HostState).where(HostState.scan_run_id == run_id)).all()
        for host in hosts:
            for port in host.ports_list:
                if port.tcp_status != "open":
                    anomalies += 1
                if port.tls_certificate and not port.tls_certificate.valid:
                    anomalies += 1
                for route in port.http_routing_checks_list:
                    if route.status_code and route.status_code >= 400:
                        anomalies += 1
                        
        run.metrics_json = {
            "total_targets_scanned": len(hosts),
            "scan_duration_seconds": duration,
            "anomalies_found": anomalies
        }
        
        session.commit()

async def run_engine_cli(run_id: str, snapshot: dict[str, Any], app_state: Any):
    if not hasattr(app_state, "log_subscribers"):
        app_state.log_subscribers = {}
    if not hasattr(app_state, "run_logs"):
        app_state.run_logs = {}
    if not hasattr(app_state, "processes"):
        app_state.processes = {}

    app_state.run_logs.setdefault(run_id, [])
    app_state.log_subscribers.setdefault(run_id, [])

    async def broadcast(event: ServerSentEvent | None):
        if event is not None:
            app_state.run_logs.setdefault(run_id, []).append(event)
        subscribers = app_state.log_subscribers.get(run_id, [])
        for q in list(subscribers):
            await q.put(event)

    try:
        with Session(db_engine) as session:
            run = session.get(ScanRun, run_id)
            if run:
                run.status = ScanRunStatus.RUNNING
                if not run.started_at:
                    run.started_at = datetime.now(timezone.utc)
                session.add(run)
                session.commit()

        cmd = [sys.executable, "-u", "-m", "engine.cli"]
        
        targets = snapshot.get("targets", [])
        if targets:
            cmd.append(",".join(targets))
            
        ports = snapshot.get("ports", [])
        if ports:
            cmd.extend(["-p", ",".join(map(str, ports))])
            
        flags = snapshot.get("flags", {})
        if isinstance(flags, dict) and "flags" in flags:
            flags = flags["flags"]
        
        fields = ExecutionFlags.model_fields
        for key, value in flags.items():
            if value is None or key not in fields:
                continue
                
            extra = fields[key].json_schema_extra or {}
            if not isinstance(extra, dict):
                continue
            cli_arg = extra.get("cli_arg")
            is_switch = extra.get("is_switch", False)
            
            if not isinstance(cli_arg, str):
                continue
                
            if is_switch and isinstance(value, bool):
                if value:
                    cmd.append(cli_arg)
                else:
                    cmd.append(cli_arg.replace("--", "--no-"))
            elif isinstance(value, list):
                for item in value:
                    cmd.extend([cli_arg, str(item)])
            else:
                cmd.extend([cli_arg, str(value)])
                
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        app_state.processes[run_id] = process
        
        # Concurrent ingestion of stdout (NDJSON data) and stderr (Logs)
        async def read_stderr():
            if not process.stderr:
                return
            while True:
                line = await process.stderr.readline()
                if not line:
                    break
                await broadcast(ServerSentEvent(data={"message": line.decode('utf-8').strip()}, event="log"))

        await asyncio.gather(
            _ingest_stdout(run_id, process),
            read_stderr()
        )
        
        await process.wait()
        
        # Determine status
        rc = process.returncode if process.returncode is not None else 1
        if rc == 130 or rc == 143:
            await broadcast(ServerSentEvent(data={"message": f"Run aborted by user"}, event="status"))
        else:
            await broadcast(ServerSentEvent(data={"message": f"Run finished with code {rc}"}, event="status"))

        await asyncio.to_thread(_finalize_run, run_id, rc)

    except Exception as e:
        await broadcast(ServerSentEvent(data={"message": f"Engine error: {e!s}"}, event="error"))
        with Session(db_engine) as session:
            run = session.get(ScanRun, run_id)
            if run:
                run.status = ScanRunStatus.FAILED
                run.finished_at = datetime.now(timezone.utc)
                session.commit()
    finally:
        if run_id in app_state.processes:
            del app_state.processes[run_id]
        await broadcast(None) # EOF marker
