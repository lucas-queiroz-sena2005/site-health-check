import asyncio
import json
import re
import sys
import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.sse import ServerSentEvent
from sqlalchemy import column
from sqlalchemy.dialects.sqlite import insert
from sqlmodel import Session, col, delete, select

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
        # 1. Upsert HostState
        metadata = data.get("metadata", {})
        host_id = f"{run_id}_{ip}"
        existing_host = session.get(HostState, host_id)

        resolved_from = metadata.get("resolved_from")
        if not resolved_from and existing_host:
            resolved_from = existing_host.metadata_resolved_from

        subrun_id = metadata.get("subrun_id")
        if not subrun_id and existing_host:
            subrun_id = existing_host.subrun_id

        new_discovered = metadata.get("discovered_from") or []
        if existing_host and existing_host.metadata_discovered_from_json:
            merged_discovered = list(dict.fromkeys(existing_host.metadata_discovered_from_json + new_discovered))
        else:
            merged_discovered = list(dict.fromkeys(new_discovered))

        stmt_host = insert(HostState).values(
            id=host_id,
            scan_run_id=run_id,
            ip_address=ip,
            metadata_resolved_from=resolved_from,
            metadata_discovered_from_json=merged_discovered,
            subrun_id=subrun_id
        ).on_conflict_do_update(
            index_elements=["scan_run_id", "ip_address"],
            set_={
                "metadata_resolved_from": resolved_from,
                "metadata_discovered_from_json": merged_discovered,
                "subrun_id": subrun_id
            }
        ).returning(column("id"))
        
        result_host = session.exec(stmt_host).first()
        host_id = f"{run_id}_{ip}" if result_host is None else str(result_host[0])

        # 2. Upsert PortState
        ports = data.get("ports", {})
        for port_str, port_data in ports.items():
            port_num = int(port_str)
            port_id = f"{host_id}_{port_num}"
            existing_port = session.get(PortState, port_id)

            incoming_tcp = port_data.get("tcp_status", "closed")
            if existing_port and existing_port.tcp_status == "open":
                final_tcp_status = "open"
            else:
                final_tcp_status = incoming_tcp

            incoming_latency = port_data.get("tcp_latency_ms")
            if incoming_latency is None and existing_port:
                final_latency = existing_port.tcp_latency_ms
            else:
                final_latency = incoming_latency

            stmt_port = insert(PortState).values(
                id=port_id,
                host_state_id=host_id,
                port_number=port_num,
                tcp_status=final_tcp_status,
                tcp_latency_ms=final_latency
            ).on_conflict_do_update(
                index_elements=["host_state_id", "port_number"],
                set_={
                    "tcp_status": final_tcp_status,
                    "tcp_latency_ms": final_latency
                }
            ).returning(column("id"))
            
            result_port = session.exec(stmt_port).first()
            port_id = f"{host_id}_{port_num}" if result_port is None else str(result_port[0])

            # 3. Handle TLS Certificates
            tls = port_data.get("tls_certificate")
            if tls:
                session.exec(
                    delete(TlsCertificate).where(column("port_state_id") == port_id)
                )
                tls_cert = TlsCertificate(
                    port_state_id=port_id,
                    valid=tls.get("valid", False),
                    expires_in_days=tls.get("expires_in_days", 0),
                    issuer=tls.get("issuer"),
                    protocol_version=tls.get("protocol_version"),
                    domains_discovered_sans_json=tls.get("domains_discovered_sans", [])
                )
                session.add(tls_cert)

            # 4. Handle Routing
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
            
        run.finished_at = datetime.now(UTC)
        
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
                started_at = started_at.replace(tzinfo=UTC)
            duration = round((run.finished_at - started_at).total_seconds(), 2)
            
        snapshot = run.execution_config_snapshot_json or {}
        ghost_window = snapshot.get("ghost_window", "7d")
        tls_warning_days = snapshot.get("tls_warning_days", 30)

        statement = select(HostState).where(HostState.scan_run_id == run_id)
        hosts = list(session.exec(statement).all())
        initial_targets_count = len(hosts)

        # 1. Resolve historical active IPs within ghost window
        historical_active_ips = set()
        match = re.fullmatch(r"^(\d+)([smhd])$", ghost_window.strip().lower())
        if match:
            amount, unit = int(match.group(1)), match.group(2)
            units = {"s": "seconds", "m": "minutes", "h": "hours", "d": "days"}
            delta = timedelta(**{units[unit]: amount})
            cutoff = datetime.now(UTC) - delta
            current_ips = [h.ip_address for h in hosts if not h.ip_address.startswith("Void")]
            if current_ips:
                historical_stmt = (
                    select(HostState.ip_address)
                    .join(PortState, col(HostState.id) == col(PortState.host_state_id))
                    .join(ScanRun, col(HostState.scan_run_id) == col(ScanRun.id))
                    .where(PortState.tcp_status == "open")
                    .where(col(ScanRun.started_at) >= cutoff)
                    .where(ScanRun.status == ScanRunStatus.COMPLETED)
                    .where(col(HostState.ip_address).in_(current_ips))
                    .distinct()
                )
                historical_active_ips = set(session.exec(historical_stmt).all())

        # 2. Classify hosts: Active, Ghost, Void
        void_host_ids: list[str] = []
        kept_hosts: list[HostState] = []

        for host in hosts:
            if host.ip_address.startswith("Void"):
                void_host_ids.append(host.id)
                continue

            has_open = any(p.tcp_status == "open" for p in host.ports)
            if has_open:
                kept_hosts.append(host)
            elif host.ip_address in historical_active_ips:
                kept_hosts.append(host)
            else:
                void_host_ids.append(host.id)

        # 3. Purge individual void hosts completely from table/database
        if void_host_ids:
            port_stmt = select(PortState.id).where(col(PortState.host_state_id).in_(void_host_ids))
            port_ids = list(session.exec(port_stmt).all())
            if port_ids:
                session.exec(delete(HttpRoutingCheck).where(col(HttpRoutingCheck.port_state_id).in_(port_ids)))
                session.exec(delete(TlsCertificate).where(col(TlsCertificate.port_state_id).in_(port_ids)))
                session.exec(delete(PortState).where(col(PortState.id).in_(port_ids)))
            session.exec(delete(HostState).where(col(HostState.id).in_(void_host_ids)))

        session.commit()

        # 4. Anomalies and operational summary
        anomalies = 0
        for host in kept_hosts:
            for port in host.ports:
                if port.tcp_status != "open":
                    anomalies += 1
                if port.tls_certificate and not port.tls_certificate.valid:
                    anomalies += 1
                for route in port.http_routing_checks:
                    if route.status_code and route.status_code >= 400:
                        anomalies += 1

        from api.services.alerts import compute_run_summary
        summary = compute_run_summary(
            session=session,
            run=run,
            ghost_window_str=ghost_window,
            tls_warning_days=tls_warning_days,
            void_count=len(void_host_ids),
        )

        run.metrics_json = {
            "total_targets_scanned": initial_targets_count,
            "scan_duration_seconds": duration,
            "anomalies_found": anomalies,
            "summary": summary,
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
                    run.started_at = datetime.now(UTC)
                session.add(run)
                session.commit()

        cmd = [sys.executable, "-u", "-m", "engine.cli", "--config", "-"]
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        if process.stdin:
            process.stdin.write(json.dumps(snapshot).encode("utf-8") + b"\n")
            await process.stdin.drain()
            process.stdin.close()
            try:
                await process.stdin.wait_closed()
            except Exception:
                pass
        
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
            await broadcast(ServerSentEvent(data={"message": "Run aborted by user"}, event="status"))
        else:
            await broadcast(ServerSentEvent(data={"message": f"Run finished with code {rc}"}, event="status"))

        await asyncio.to_thread(_finalize_run, run_id, rc)

    except Exception as e:  # noqa: BLE001
        await broadcast(ServerSentEvent(data={"message": f"Engine error: {e!s}"}, event="error"))
        with Session(db_engine) as session:
            run = session.get(ScanRun, run_id)
            if run:
                run.status = ScanRunStatus.FAILED
                run.finished_at = datetime.now(UTC)
                session.commit()
    finally:
        if run_id in app_state.processes:
            del app_state.processes[run_id]
        await broadcast(None) # EOF marker
