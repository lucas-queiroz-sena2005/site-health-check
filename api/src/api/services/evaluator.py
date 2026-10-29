from datetime import datetime, timedelta, timezone
import re
from sqlalchemy import column, func, or_, update
from sqlalchemy.orm import selectinload
from sqlmodel import Session, col, delete, select

from api.models import (
    EntityStatus,
    HostState,
    HttpRoutingCheck,
    PortState,
    ScanRun,
    ScanRunStatus,
    TlsCertificate,
)
from api.services.evaluator_rules import (
    FINDING_HOST_GHOST,
    FINDING_HOST_VOID,
    FINDING_HTTP_4XX,
    FINDING_HTTP_5XX,
    FINDING_HTTP_ERROR,
    FINDING_RUN_ABORTED,
    FINDING_TCP_CLOSED,
    FINDING_TLS_DEPRECATED_VERSION,
    FINDING_TLS_EXPIRED,
    FINDING_TLS_EXPIRING_SOON,
    FINDING_TLS_INVALID,
    evaluate_host_status,
    evaluate_http_check,
    evaluate_port,
    evaluate_tls_cert,
    is_deprecated_tls,
)

_TLS_VERSION_RANK = {
    "SSLv2": 1,
    "SSLv3": 2,
    "TLSv1": 3,
    "TLSv1.0": 3,
    "TLSv1.1": 4,
    "TLSv1.2": 5,
    "TLSv1.3": 6,
}


def _parse_ghost_window(window_str: str | None) -> timedelta | None:
    if not window_str:
        return timedelta(days=7)
    m = re.fullmatch(r"^(\d+)([smhd])$", window_str.strip().lower())
    if not m:
        return None
    amount, unit = int(m.group(1)), m.group(2)
    units = {"s": "seconds", "m": "minutes", "h": "hours", "d": "days"}
    return timedelta(**{units[unit]: amount})


def evaluate_scan_run(
    scan_run_id: str,
    session: Session,
    void_count: int | None = None,
    ghost_window_override: str | None = None,
    tls_warning_days_override: int | None = None,
) -> dict[str, int]:
    """Bottom-up deterministic evaluation pipeline per ADR 0023 and ADR 0024.

    Computes Level 1 (HttpRoutingCheck) -> Level 2 (PortState) -> Level 3 (HostState)
    finding codes, statuses, rollups, and ScanRun.metrics_json["summary"] in one pass.
    Utilizes SQL subqueries and set-based operations to avoid SQLite variable limits at /16 scale.
    """
    default_summary = {
        "active": 0,
        "warning": 0,
        "failed": 0,
        "ghost": 0,
        "void": void_count or 0,
        "service_count": 0,
        "http_check_count": 0,
    }
    run = session.get(ScanRun, scan_run_id)
    if not run:
        return default_summary

    snapshot = run.execution_config_snapshot_json or {}
    ghost_window_str = (
        ghost_window_override
        if ghost_window_override is not None
        else (snapshot.get("ghost_window") or "7d")
    )
    tls_warning_days = int(
        tls_warning_days_override
        if tls_warning_days_override is not None
        else (snapshot.get("tls_warning_days") or 30)
    )
    prune_void_hosts = bool(snapshot.get("prune_void_hosts", True))
    prune_closed_ports = bool(snapshot.get("prune_closed_ports", True))

    # 1. Determine historical active (ip, port) pairs via SQL subquery (avoiding Python IP lists)
    historical_active_ip_ports: set[tuple[str, int]] = set()
    historical_active_ips: set[str] = set()
    ghost_window_td = _parse_ghost_window(ghost_window_str)

    current_run_ips_subq = (
        select(HostState.ip_address)
        .where(HostState.scan_run_id == scan_run_id)
    )

    if ghost_window_td is not None and run.scan_id is not None:
        now_dt = run.started_at or datetime.now(timezone.utc)
        if now_dt.tzinfo is None:
            now_dt = now_dt.replace(tzinfo=timezone.utc)
        cutoff = now_dt - ghost_window_td

        hist_stmt = (
            select(HostState.ip_address, PortState.port_number)
            .join(PortState, col(HostState.id) == col(PortState.host_state_id))
            .join(ScanRun, col(HostState.scan_run_id) == col(ScanRun.id))
            .where(PortState.tcp_status == "open")
            .where(col(ScanRun.started_at) >= cutoff)
            .where(ScanRun.status == ScanRunStatus.COMPLETED)
            .where(col(ScanRun.id) != scan_run_id)
            .where(ScanRun.scan_id == run.scan_id)
            .where(col(HostState.ip_address).in_(current_run_ips_subq))
            .distinct()
        )
        historical_active_ip_ports = set(session.exec(hist_stmt).all())
        historical_active_ips = {ip for ip, _ in historical_active_ip_ports}

    # 2. Relational pushdown: Identify candidate hosts vs pure routine void hosts
    candidate_or_conditions = [
        HostState.id.in_(
            select(PortState.host_state_id).where(PortState.tcp_status != "closed")
        ),
        HostState.id.in_(
            select(PortState.host_state_id).join(
                TlsCertificate, col(PortState.id) == col(TlsCertificate.port_state_id)
            )
        ),
        HostState.id.in_(
            select(PortState.host_state_id).join(
                HttpRoutingCheck,
                col(PortState.id) == col(HttpRoutingCheck.port_state_id),
            )
        ),
    ]
    if historical_active_ips:
        candidate_or_conditions.append(HostState.ip_address.in_(historical_active_ips))

    candidate_host_subq = (
        select(HostState.id)
        .where(HostState.scan_run_id == scan_run_id)
        .where(or_(*candidate_or_conditions))
    )

    pure_void_subq = (
        select(HostState.id)
        .where(HostState.scan_run_id == scan_run_id)
        .where(~HostState.id.in_(candidate_host_subq))
    )

    pure_void_count = (
        session.exec(
            select(func.count())
            .select_from(HostState)
            .where(HostState.scan_run_id == scan_run_id)
            .where(~HostState.id.in_(candidate_host_subq))
        ).one()
        or 0
    )

    # 3. Handle pure routine void hosts fast-path (SQL set-based)
    if prune_void_hosts:
        if pure_void_count > 0:
            pure_void_ports_subq = (
                select(PortState.id).where(PortState.host_state_id.in_(pure_void_subq))
            )
            session.exec(delete(PortState).where(PortState.id.in_(pure_void_ports_subq)))
            session.exec(delete(HostState).where(HostState.id.in_(pure_void_subq)))
    else:
        if pure_void_count > 0:
            session.exec(
                update(HostState)
                .where(HostState.scan_run_id == scan_run_id)
                .where(~HostState.id.in_(candidate_host_subq))
                .values(
                    status=EntityStatus.VOID,
                    finding_codes=[],
                    open_port_count=0,
                    vhost_count=0,
                    depth=0,
                )
            )
            pure_void_ports_subq = (
                select(PortState.id).where(PortState.host_state_id.in_(pure_void_subq))
            )
            session.exec(
                update(PortState)
                .where(PortState.id.in_(pure_void_ports_subq))
                .values(
                    status=EntityStatus.VOID,
                    finding_codes=[FINDING_TCP_CLOSED],
                )
            )

    # 4. Load remaining candidate hosts with eager loading for detailed rule evaluation
    candidate_hosts_stmt = (
        select(HostState)
        .where(HostState.scan_run_id == scan_run_id)
        .where(HostState.id.in_(candidate_host_subq))
        .options(
            selectinload(HostState.ports).selectinload(PortState.tls_certificate),
            selectinload(HostState.ports).selectinload(PortState.http_routing_checks),
        )
    )
    candidate_hosts = list(session.exec(candidate_hosts_stmt).all())

    candidate_void_count = 0

    for host in candidate_hosts:
        open_ports: list[PortState] = []
        host_findings: list[str] = []
        worst_http_statuses_on_host: list[int] = []
        tls_versions_on_host: list[str] = []
        min_tls_days_list: list[int] = []
        has_ghost_port = False

        for port in host.ports:
            port_check_statuses: list[str] = []
            port_check_findings: list[str] = []
            worst_http_status_on_port: int | None = None

            # Level 1: HTTP routing checks
            for check in port.http_routing_checks:
                check.status, check.finding_code = evaluate_http_check(check.status_code)
                port_check_statuses.append(check.status)
                if check.finding_code and check.finding_code not in port_check_findings:
                    port_check_findings.append(check.finding_code)

                if check.status_code is not None:
                    if worst_http_status_on_port is None or check.status_code > worst_http_status_on_port:
                        worst_http_status_on_port = check.status_code
                    worst_http_statuses_on_host.append(check.status_code)
                session.add(check)

            # Level 2: Port rollups & TLS cert evaluation
            port.san_count = (
                len(port.tls_certificate.domains_discovered_sans_json)
                if port.tls_certificate and port.tls_certificate.domains_discovered_sans_json
                else 0
            )
            port.http_check_count = len(port.http_routing_checks)
            port.worst_http_status = worst_http_status_on_port

            tls_findings: list[str] = []
            if port.tls_certificate:
                cert = port.tls_certificate
                if cert.protocol_version:
                    tls_versions_on_host.append(cert.protocol_version)

                tls_findings, cert_min_days = evaluate_tls_cert(
                    valid=cert.valid,
                    expires_in_days=cert.expires_in_days,
                    protocol_version=cert.protocol_version,
                    tls_warning_days=tls_warning_days,
                )
                if cert_min_days is not None:
                    min_tls_days_list.append(cert_min_days)

            was_port_hist_open = (
                host.ip_address,
                port.port_number,
            ) in historical_active_ip_ports

            port_status, port_findings, is_ghost = evaluate_port(
                tcp_status=port.tcp_status,
                check_statuses=port_check_statuses,
                check_findings=port_check_findings,
                tls_findings=tls_findings,
                was_historically_open=was_port_hist_open,
            )
            port.status = port_status
            port.finding_codes = port_findings

            if port.tcp_status == "open":
                open_ports.append(port)
            if is_ghost:
                has_ghost_port = True
                if FINDING_HOST_GHOST not in host_findings:
                    host_findings.append(FINDING_HOST_GHOST)

            for f in port_findings:
                if f != FINDING_TCP_CLOSED and f not in host_findings:
                    host_findings.append(f)

            session.add(port)

        # Level 3: Host rollups
        filtered_disc = [d for d in (host.discovered_from or []) if d != host.ip_address]
        host.depth = len(filtered_disc)
        host.vhost_count = len(host.resolved_domains or [])
        host.scanned_port_count = max(host.scanned_port_count or 0, len(host.ports))
        host.open_port_count = len(open_ports)

        latencies = [p.tcp_latency_ms for p in open_ports if p.tcp_latency_ms is not None]
        host.min_tcp_latency_ms = min(latencies) if latencies else None
        host.min_tls_expires_days = min(min_tls_days_list) if min_tls_days_list else None

        if tls_versions_on_host:
            host.worst_tls_version = min(
                tls_versions_on_host,
                key=lambda v: _TLS_VERSION_RANK.get(v.strip(), 5),
            )
        else:
            host.worst_tls_version = None

        host.worst_http_status = (
            max(worst_http_statuses_on_host) if worst_http_statuses_on_host else None
        )

        has_error_port = any(p.tcp_status == "error" for p in host.ports)
        open_port_statuses = [p.status for p in open_ports]

        was_ip_hist_active = host.ip_address in historical_active_ips

        host_status, host_findings = evaluate_host_status(
            open_port_count=host.open_port_count,
            open_port_statuses=open_port_statuses,
            has_error_port=has_error_port,
            has_ghost_port=has_ghost_port,
            was_ip_historically_active=was_ip_hist_active,
            initial_findings=host_findings,
        )
        host.status = host_status
        host.finding_codes = host_findings

        if host.status == EntityStatus.VOID:
            candidate_void_count += 1

        session.add(host)

    # Flush changes to candidate hosts so subsequent queries and pruning reflect new statuses
    session.flush()

    # 5. Pruning for candidate hosts
    if prune_void_hosts:
        void_cand_host_subq = (
            select(HostState.id)
            .where(HostState.scan_run_id == scan_run_id)
            .where(HostState.status == EntityStatus.VOID)
        )
        void_cand_ports_subq = (
            select(PortState.id).where(PortState.host_state_id.in_(void_cand_host_subq))
        )
        session.exec(delete(HttpRoutingCheck).where(HttpRoutingCheck.port_state_id.in_(void_cand_ports_subq)))
        session.exec(delete(TlsCertificate).where(TlsCertificate.port_state_id.in_(void_cand_ports_subq)))
        session.exec(delete(PortState).where(PortState.id.in_(void_cand_ports_subq)))
        session.exec(delete(HostState).where(HostState.id.in_(void_cand_host_subq)))

    if prune_closed_ports:
        routine_closed_port_subq = (
            select(PortState.id)
            .join(HostState, col(PortState.host_state_id) == col(HostState.id))
            .where(HostState.scan_run_id == scan_run_id)
            .where(HostState.status != EntityStatus.VOID)
            .where(PortState.status == EntityStatus.VOID)
        )
        session.exec(delete(HttpRoutingCheck).where(HttpRoutingCheck.port_state_id.in_(routine_closed_port_subq)))
        session.exec(delete(TlsCertificate).where(TlsCertificate.port_state_id.in_(routine_closed_port_subq)))
        session.exec(delete(PortState).where(PortState.id.in_(routine_closed_port_subq)))

    # 6. SQL aggregations for summary metrics
    active_count = (
        session.exec(
            select(func.count())
            .select_from(HostState)
            .where(
                HostState.scan_run_id == scan_run_id,
                HostState.open_port_count > 0,
                HostState.status == EntityStatus.OK,
            )
        ).one()
        or 0
    )

    warning_count = (
        session.exec(
            select(func.count())
            .select_from(HostState)
            .where(
                HostState.scan_run_id == scan_run_id,
                HostState.open_port_count > 0,
                HostState.status == EntityStatus.WARNING,
            )
        ).one()
        or 0
    )

    failed_count = (
        session.exec(
            select(func.count())
            .select_from(HostState)
            .where(
                HostState.scan_run_id == scan_run_id,
                HostState.open_port_count > 0,
                HostState.status == EntityStatus.FAILED,
            )
        ).one()
        or 0
    )

    ghost_count = (
        session.exec(
            select(func.count())
            .select_from(HostState)
            .where(
                HostState.scan_run_id == scan_run_id,
                HostState.status == EntityStatus.GHOST,
            )
        ).one()
        or 0
    )

    existing_void = (
        int(run.metrics_json["summary"]["void"])
        if run.metrics_json
        and isinstance(run.metrics_json, dict)
        and isinstance(run.metrics_json.get("summary"), dict)
        and "void" in run.metrics_json["summary"]
        else None
    )

    total_void_found = pure_void_count + candidate_void_count
    final_void = (
        void_count
        if void_count is not None
        else (existing_void if existing_void is not None else total_void_found)
    )

    total_service_count = (
        session.exec(
            select(func.count())
            .select_from(PortState)
            .join(HostState, col(PortState.host_state_id) == col(HostState.id))
            .where(
                HostState.scan_run_id == scan_run_id,
                PortState.status != EntityStatus.VOID,
            )
        ).one()
        or 0
    )

    total_http_check_count = (
        session.exec(
            select(func.count())
            .select_from(HttpRoutingCheck)
            .join(PortState, col(HttpRoutingCheck.port_state_id) == col(PortState.id))
            .join(HostState, col(PortState.host_state_id) == col(HostState.id))
            .where(HostState.scan_run_id == scan_run_id)
        ).one()
        or 0
    )

    summary = {
        "active": active_count,
        "warning": warning_count,
        "failed": failed_count,
        "ghost": ghost_count,
        "void": final_void,
        "service_count": total_service_count,
        "http_check_count": total_http_check_count,
    }

    metrics = dict(run.metrics_json or {})
    metrics["summary"] = summary
    run.metrics_json = metrics
    session.add(run)
    session.commit()

    return summary
