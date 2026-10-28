import asyncio
import ipaddress
import json
import re
import sys
import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.sse import ServerSentEvent
from sqlalchemy import column, func
from sqlalchemy.dialects.sqlite import insert
from sqlmodel import Session, col, delete, select

from api.database import engine as db_engine
from api.models import (
    HostState,
    HttpRoutingCheck,
    PortState,
    ScanRun,
    ScanRunStatus,
    TlsCertificate,
    compute_ip_sort_key,
)


def _bulk_upsert_deltas_sync(run_id: str, batch: list[tuple[str, dict[str, Any]]]):
    """Sync function to bulk upsert a batch of NDJSON deltas into SQLite within a single transaction,
    performing in-batch delta coalescing to preserve lineage and sticky open port states.
    """
    if not batch:
        return

    # 1. In-Batch Delta Coalescing
    coalesced: dict[str, dict[str, Any]] = {}
    for ip, data in batch:
        if ip not in coalesced:
            coalesced[ip] = {
                "metadata": dict(data.get("metadata", {})),
                "ports": {p: dict(pdata) for p, pdata in data.get("ports", {}).items()},
            }
            meta = coalesced[ip]["metadata"]
            res = meta.get("resolved_domains")
            if res is None:
                rf = meta.get("resolved_from")
                meta["resolved_domains"] = [rf] if rf else []
            elif isinstance(res, str):
                meta["resolved_domains"] = [res]
            else:
                meta["resolved_domains"] = list(res)

            disc = meta.get("discovered_from") or []
            if isinstance(disc, str):
                meta["discovered_from"] = [disc]
            else:
                meta["discovered_from"] = list(disc)
        else:
            existing = coalesced[ip]
            new_meta = data.get("metadata", {})
            subrun = new_meta.get("subrun_id")
            if subrun:
                existing["metadata"]["subrun_id"] = subrun

            new_res = new_meta.get("resolved_domains")
            if new_res is None:
                rf = new_meta.get("resolved_from")
                new_res_list = [rf] if rf else []
            elif isinstance(new_res, str):
                new_res_list = [new_res]
            else:
                new_res_list = list(new_res)
            existing["metadata"]["resolved_domains"] = list(
                dict.fromkeys(existing["metadata"]["resolved_domains"] + new_res_list)
            )

            new_disc = new_meta.get("discovered_from") or []
            if isinstance(new_disc, str):
                new_disc_list = [new_disc]
            else:
                new_disc_list = list(new_disc)
            existing["metadata"]["discovered_from"] = list(
                dict.fromkeys(existing["metadata"]["discovered_from"] + new_disc_list)
            )

            new_ports = data.get("ports", {})
            for port_str, pdata in new_ports.items():
                if port_str not in existing["ports"]:
                    existing["ports"][port_str] = dict(pdata)
                else:
                    ep = existing["ports"][port_str]
                    incoming_tcp = pdata.get("tcp_status", "closed")
                    if ep.get("tcp_status") == "open" or incoming_tcp == "open":
                        ep["tcp_status"] = "open"
                    else:
                        ep["tcp_status"] = incoming_tcp

                    if pdata.get("tcp_latency_ms") is not None:
                        ep["tcp_latency_ms"] = pdata.get("tcp_latency_ms")

                    if pdata.get("tls_certificate"):
                        ep["tls_certificate"] = pdata["tls_certificate"]

                    if pdata.get("http_routing_checks"):
                        existing_routing = ep.setdefault("http_routing_checks", {})
                        existing_routing.update(pdata["http_routing_checks"])

    # 2. Write coalesced batch to SQLite in a single transaction
    with Session(db_engine) as session:
        for ip, data in coalesced.items():
            metadata = data.get("metadata", {})
            host_id = f"{run_id}_{ip}"
            existing_host = session.get(HostState, host_id)

            incoming_resolved = metadata.get("resolved_domains", [])
            if existing_host and existing_host.resolved_domains:
                merged_resolved = list(
                    dict.fromkeys(existing_host.resolved_domains + incoming_resolved)
                )
            else:
                merged_resolved = list(dict.fromkeys(incoming_resolved))

            subrun_id = metadata.get("subrun_id")
            if not subrun_id and existing_host:
                subrun_id = existing_host.subrun_id

            incoming_discovered = metadata.get("discovered_from", [])
            if existing_host and existing_host.discovered_from:
                merged_discovered = list(
                    dict.fromkeys(existing_host.discovered_from + incoming_discovered)
                )
            else:
                merged_discovered = list(dict.fromkeys(incoming_discovered))

            filtered_lineage = [d for d in merged_discovered if d != ip]
            depth = len(filtered_lineage)
            sort_key = compute_ip_sort_key(ip)

            stmt_host = (
                insert(HostState)
                .values(
                    id=host_id,
                    scan_run_id=run_id,
                    ip_address=ip,
                    ip_sort_key=sort_key,
                    resolved_domains=merged_resolved,
                    discovered_from=merged_discovered,
                    depth=depth,
                    subrun_id=subrun_id,
                )
                .on_conflict_do_update(
                    index_elements=["scan_run_id", "ip_address"],
                    set_={
                        "ip_sort_key": sort_key,
                        "resolved_domains": merged_resolved,
                        "discovered_from": merged_discovered,
                        "depth": depth,
                        "subrun_id": subrun_id,
                    },
                )
                .returning(column("id"))
            )

            result_host = session.exec(stmt_host).first()
            host_id = f"{run_id}_{ip}" if result_host is None else str(result_host[0])

            # Upsert PortState
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

                stmt_port = (
                    insert(PortState)
                    .values(
                        id=port_id,
                        host_state_id=host_id,
                        port_number=port_num,
                        tcp_status=final_tcp_status,
                        tcp_latency_ms=final_latency,
                    )
                    .on_conflict_do_update(
                        index_elements=["host_state_id", "port_number"],
                        set_={
                            "tcp_status": final_tcp_status,
                            "tcp_latency_ms": final_latency,
                        },
                    )
                    .returning(column("id"))
                )

                result_port = session.exec(stmt_port).first()
                port_id = (
                    f"{host_id}_{port_num}" if result_port is None else str(result_port[0])
                )

                # Handle TLS Certificates
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
                        domains_discovered_sans_json=tls.get(
                            "domains_discovered_sans", []
                        ),
                    )
                    session.add(tls_cert)

                # Handle Routing
                routing = port_data.get("http_routing_checks", {})
                for domain, r_data in routing.items():
                    stmt_route = (
                        insert(HttpRoutingCheck)
                        .values(
                            id=f"{port_id}_{domain}",
                            port_state_id=port_id,
                            domain=domain,
                            status_code=r_data.get("status_code"),
                            http_latency_ms=r_data.get("http_latency_ms"),
                            path_checked=r_data.get("path_checked", "/"),
                            redirects_to_url=r_data.get("redirects_to_url"),
                            server_header=r_data.get("server_header"),
                            notes=r_data.get("notes"),
                        )
                        .on_conflict_do_update(
                            index_elements=["port_state_id", "domain"],
                            set_={
                                "status_code": r_data.get("status_code"),
                                "http_latency_ms": r_data.get("http_latency_ms"),
                                "path_checked": r_data.get("path_checked", "/"),
                                "redirects_to_url": r_data.get("redirects_to_url"),
                                "server_header": r_data.get("server_header"),
                                "notes": r_data.get("notes"),
                            },
                        )
                    )
                    session.exec(stmt_route)

        session.commit()


def _upsert_delta_sync(run_id: str, ip: str, data: dict[str, Any]):
    """Wrapper around _bulk_upsert_deltas_sync for single-delta ingestion."""
    _bulk_upsert_deltas_sync(run_id, [(ip, data)])


async def _ingest_stdout(
    run_id: str,
    process: asyncio.subprocess.Process,
    publish_log: Any = None,
):
    if not process.stdout:
        return

    seen_ips: set[str] = set()
    seen_active_ips: set[str] = set()
    batch: list[tuple[str, dict[str, Any]]] = []
    batch_size = 500

    while True:
        line = await process.stdout.readline()
        if not line:
            break

        line_str = line.decode("utf-8").strip()
        if not line_str:
            continue

        try:
            payload = json.loads(line_str)
            # Check if this is the final summary line
            if "status" in payload:
                # The process might be done or aborted, we let the main loop handle the final state update.
                continue

            # Otherwise it's deltas
            for ip, data in payload.items():
                batch.append((ip, data))
                is_new_ip = ip not in seen_ips
                seen_ips.add(ip)

                if publish_log is not None:
                    ports_dict = data.get("ports", {})
                    open_ports = [
                        str(p)
                        for p, pdata in ports_dict.items()
                        if isinstance(pdata, dict) and pdata.get("tcp_status") == "open"
                    ]
                    if open_ports and ip not in seen_active_ips:
                        seen_active_ips.add(ip)
                        publish_log(
                            ServerSentEvent(
                                data={
                                    "message": f"[+] Active host {ip} (open: {', '.join(open_ports)})"
                                },
                                event="log",
                            )
                        )
                    if is_new_ip and len(seen_ips) % 250 == 0:
                        publish_log(
                            ServerSentEvent(
                                data={
                                    "message": f"[~] Progress: {len(seen_ips)} IPs probed ({len(seen_active_ips)} responsive)..."
                                },
                                event="log",
                            )
                        )

            if len(batch) >= batch_size:
                await asyncio.to_thread(_bulk_upsert_deltas_sync, run_id, batch)
                batch = []
        except json.JSONDecodeError:
            pass

    if batch:
        await asyncio.to_thread(_bulk_upsert_deltas_sync, run_id, batch)
        batch = []


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

        initial_targets_count = (
            session.exec(
                select(func.count())
                .select_from(HostState)
                .where(HostState.scan_run_id == run_id)
            ).one()
            or 0
        )

        # Deterministic Backend Evaluation & Pruning Pipeline (Single Source of Truth)
        from api.services.evaluator import evaluate_scan_run

        summary = evaluate_scan_run(
            run_id,
            session,
            ghost_window_override=ghost_window,
            tls_warning_days_override=tls_warning_days,
        )

        anomalies = (
            summary.get("warning", 0)
            + summary.get("failed", 0)
            + summary.get("ghost", 0)
        )

        existing_metrics = dict(run.metrics_json or {})
        existing_metrics.update({
            "total_targets_scanned": initial_targets_count,
            "scan_duration_seconds": duration,
            "anomalies_found": anomalies,
            "summary": summary,
        })
        run.metrics_json = existing_metrics
        session.add(run)
        session.commit()

