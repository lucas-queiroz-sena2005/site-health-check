from datetime import UTC, datetime, timedelta
import re
from typing import Any
from sqlmodel import Session, col, select

from api.models import (
    HostState,
    HttpRoutingCheck,
    PortState,
    ScanRun,
    ScanRunStatus,
    TlsCertificate,
)

# Canonical Finding Codes per ADR 0023
FINDING_TCP_CLOSED = "TCP_CLOSED"
FINDING_TLS_INVALID = "TLS_INVALID"
FINDING_TLS_EXPIRED = "TLS_EXPIRED"
FINDING_TLS_EXPIRING_SOON = "TLS_EXPIRING_SOON"
FINDING_TLS_DEPRECATED_VERSION = "TLS_DEPRECATED_VERSION"
FINDING_HTTP_5XX = "HTTP_5XX"
FINDING_HTTP_4XX = "HTTP_4XX"
FINDING_HTTP_ERROR = "HTTP_ERROR"
FINDING_HOST_GHOST = "HOST_GHOST"
FINDING_HOST_VOID = "HOST_VOID"
FINDING_RUN_ABORTED = "RUN_ABORTED"

_TLS_VERSION_RANK = {
    "SSLv2": 1,
    "SSLv3": 2,
    "TLSv1": 3,
    "TLSv1.0": 3,
    "TLSv1.1": 4,
    "TLSv1.2": 5,
    "TLSv1.3": 6,
}


def _is_deprecated_tls(version: str | None) -> bool:
    if not version:
        return False
    v = version.strip()
    return _TLS_VERSION_RANK.get(v, 5) < 5


def _parse_ghost_window(window_str: str | None) -> timedelta:
    if not window_str:
        return timedelta(days=7)
    m = re.fullmatch(r"^(\d+)([smhd])$", window_str.strip().lower())
    if not m:
        return timedelta(days=7)
    amount, unit = int(m.group(1)), m.group(2)
    units = {"s": "seconds", "m": "minutes", "h": "hours", "d": "days"}
    return timedelta(**{units[unit]: amount})


def evaluate_scan_run(scan_run_id: str, session: Session) -> None:
    """Bottom-up deterministic evaluation pipeline per ADR 0023 Track 2.
    Computes Level 1 (HttpRoutingCheck) -> Level 2 (PortState) -> Level 3 (HostState)
    finding codes, statuses, and rollups before committing final state.
    """
    run = session.get(ScanRun, scan_run_id)
    if not run:
        return

    snapshot = run.execution_config_snapshot_json or {}
    ghost_window_str = snapshot.get("ghost_window") or "7d"
    tls_warning_days = int(snapshot.get("tls_warning_days") or 30)

    # Determine historical active IPs for ghost detection
    ghost_window_td = _parse_ghost_window(ghost_window_str)
    now_dt = run.started_at or datetime.now(UTC)
    if now_dt.tzinfo is None:
        now_dt = now_dt.replace(tzinfo=UTC)
    cutoff = now_dt - ghost_window_td

    stmt_hosts = select(HostState).where(HostState.scan_run_id == scan_run_id)
    hosts = session.exec(stmt_hosts).all()
    if not hosts:
        return

    host_ips = [h.ip_address for h in hosts]

    hist_stmt = (
        select(HostState.ip_address)
        .join(PortState, col(HostState.id) == col(PortState.host_state_id))
        .join(ScanRun, col(HostState.scan_run_id) == col(ScanRun.id))
        .where(PortState.tcp_status == "open")
        .where(col(ScanRun.started_at) >= cutoff)
        .where(ScanRun.status == ScanRunStatus.COMPLETED)
        .where(col(HostState.ip_address).in_(host_ips))
        .distinct()
    )
    historical_active_ips = set(session.exec(hist_stmt).all())

    for host in hosts:
        open_ports: list[PortState] = []
        host_findings: list[str] = []
        worst_http_statuses_on_host: list[int] = []
        tls_versions_on_host: list[str] = []
        min_tls_days_list: list[int] = []

        # Process each port (Level 2) and its checks (Level 1)
        for port in host.ports:
            port_findings: list[str] = []
            check_statuses: list[str] = []
            worst_http_status_on_port: int | None = None

            # Level 1: HTTP checks
            for check in port.http_routing_checks:
                if check.status_code is None:
                    check.status = "failed"
                    check.finding_code = FINDING_HTTP_ERROR
                elif check.status_code >= 500:
                    check.status = "failed"
                    check.finding_code = FINDING_HTTP_5XX
                elif check.status_code >= 400:
                    check.status = "warning"
                    check.finding_code = FINDING_HTTP_4XX
                else:
                    check.status = "ok"
                    check.finding_code = None

                check_statuses.append(check.status)
                if check.finding_code and check.finding_code not in port_findings:
                    port_findings.append(check.finding_code)

                if check.status_code is not None:
                    if worst_http_status_on_port is None or check.status_code > worst_http_status_on_port:
                        worst_http_status_on_port = check.status_code
                    worst_http_statuses_on_host.append(check.status_code)
                session.add(check)

            # Level 2: Port rollups
            port.san_count = (
                len(port.tls_certificate.domains_discovered_sans_json)
                if port.tls_certificate and port.tls_certificate.domains_discovered_sans_json
                else 0
            )
            port.http_check_count = len(port.http_routing_checks)
            port.worst_http_status = worst_http_status_on_port

            is_open = port.tcp_status == "open"
            if not is_open:
                if FINDING_TCP_CLOSED not in port_findings:
                    port_findings.append(FINDING_TCP_CLOSED)
                port.status = "failed"
            else:
                open_ports.append(port)
                # TLS Certificate evaluation
                cert = port.tls_certificate
                if cert:
                    if cert.protocol_version:
                        tls_versions_on_host.append(cert.protocol_version)

                    if not cert.valid:
                        port_findings.append(FINDING_TLS_INVALID)
                    elif cert.expires_in_days <= 0:
                        port_findings.append(FINDING_TLS_EXPIRED)
                    elif cert.expires_in_days <= tls_warning_days:
                        port_findings.append(FINDING_TLS_EXPIRING_SOON)
                        min_tls_days_list.append(cert.expires_in_days)
                    else:
                        min_tls_days_list.append(cert.expires_in_days)

                    if _is_deprecated_tls(cert.protocol_version):
                        port_findings.append(FINDING_TLS_DEPRECATED_VERSION)

                # Assign Port status
                has_port_failure = (
                    any(s == "failed" for s in check_statuses)
                    or FINDING_TLS_INVALID in port_findings
                    or FINDING_TLS_EXPIRED in port_findings
                )
                has_port_warning = (
                    any(s == "warning" for s in check_statuses)
                    or FINDING_TLS_EXPIRING_SOON in port_findings
                    or FINDING_TLS_DEPRECATED_VERSION in port_findings
                )

                if has_port_failure:
                    port.status = "failed"
                elif has_port_warning:
                    port.status = "warning"
                else:
                    port.status = "ok"

            port.finding_codes = port_findings
            session.add(port)

            for f in port_findings:
                if f not in host_findings:
                    host_findings.append(f)

        # Level 3: HostState rollups
        filtered_disc = [d for d in host.discovered_from if d != host.ip_address]
        host.depth = len(filtered_disc)
        host.vhost_count = len(host.resolved_domains)
        host.scanned_port_count = len(host.ports)
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

        # Host status evaluation
        if host.open_port_count == 0:
            if host.ip_address in historical_active_ips:
                host.status = "ghost"
                if FINDING_HOST_GHOST not in host_findings:
                    host_findings.append(FINDING_HOST_GHOST)
            else:
                host.status = "failed" if any(p.status == "failed" for p in host.ports) else "ok"
        else:
            if any(p.status == "failed" for p in host.ports):
                host.status = "failed"
            elif any(p.status == "warning" for p in host.ports):
                host.status = "warning"
            else:
                host.status = "ok"

        host.finding_codes = host_findings
        session.add(host)

    session.commit()
