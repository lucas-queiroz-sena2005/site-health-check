"""Pure, stateless rule engine for health check evaluation per ADR 0023 and ADR 0024.

Zero database dependencies or side-effects.
"""

from typing import Any

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

_TLS_VERSION_RANK: dict[str, int] = {
    "SSLv2": 1,
    "SSLv3": 2,
    "TLSv1": 3,
    "TLSv1.0": 3,
    "TLSv1.1": 4,
    "TLSv1.2": 5,
    "TLSv1.3": 6,
}


def is_deprecated_tls(version: str | None) -> bool:
    """Returns True if TLS version is deprecated (below TLSv1.2)."""
    if not version:
        return False
    v = version.strip()
    return _TLS_VERSION_RANK.get(v, 5) < 5


def evaluate_http_check(status_code: int | None) -> tuple[str, str | None]:
    """Evaluates an HTTP check status code.

    Returns:
        (status, finding_code) where status is 'ok', 'warning', or 'failed'.
    """
    if status_code is None:
        return "failed", FINDING_HTTP_ERROR
    if status_code >= 500:
        return "failed", FINDING_HTTP_5XX
    if status_code >= 400:
        return "warning", FINDING_HTTP_4XX
    return "ok", None


def evaluate_tls_cert(
    valid: bool,
    expires_in_days: int,
    protocol_version: str | None,
    tls_warning_days: int = 30,
) -> tuple[list[str], int | None]:
    """Evaluates a TLS certificate's validity, expiration, and protocol version.

    Returns:
        (findings, min_days) where min_days is expires_in_days if valid, or None if invalid/expired.
    """
    findings: list[str] = []
    min_days: int | None = None

    if not valid:
        findings.append(FINDING_TLS_INVALID)
    elif expires_in_days <= 0:
        findings.append(FINDING_TLS_EXPIRED)
    elif expires_in_days <= tls_warning_days:
        findings.append(FINDING_TLS_EXPIRING_SOON)
        min_days = expires_in_days
    else:
        min_days = expires_in_days

    if is_deprecated_tls(protocol_version):
        findings.append(FINDING_TLS_DEPRECATED_VERSION)

    return findings, min_days


def evaluate_port(
    tcp_status: str,
    check_statuses: list[str],
    check_findings: list[str],
    tls_findings: list[str],
    was_historically_open: bool,
) -> tuple[str, list[str], bool]:
    """Evaluates a port given its TCP state, HTTP checks, TLS cert findings, and historical baseline.

    Returns:
        (port_status, port_findings, is_ghost_port) where port_status is 'ok', 'warning', 'failed', 'ghost', or 'void'.
    """
    port_findings: list[str] = list(dict.fromkeys(check_findings + tls_findings))

    if tcp_status != "open":
        if FINDING_TCP_CLOSED not in port_findings:
            port_findings.append(FINDING_TCP_CLOSED)

        if was_historically_open:
            if FINDING_HOST_GHOST not in port_findings:
                port_findings.append(FINDING_HOST_GHOST)
            return "ghost", port_findings, True
        else:
            return "void", port_findings, False

    # Open TCP port evaluation
    has_failure = (
        any(s == "failed" for s in check_statuses)
        or FINDING_TLS_INVALID in tls_findings
        or FINDING_TLS_EXPIRED in tls_findings
    )
    has_warning = (
        any(s == "warning" for s in check_statuses)
        or FINDING_TLS_EXPIRING_SOON in tls_findings
        or FINDING_TLS_DEPRECATED_VERSION in tls_findings
    )

    if has_failure:
        port_status = "failed"
    elif has_warning:
        port_status = "warning"
    else:
        port_status = "ok"

    return port_status, port_findings, False


def evaluate_host_status(
    open_port_count: int,
    open_port_statuses: list[str],
    has_error_port: bool,
    has_ghost_port: bool,
    was_ip_historically_active: bool,
    initial_findings: list[str] | None = None,
) -> tuple[str, list[str]]:
    """Evaluates a host's rolled-up status from its ports and historical activity.

    Returns:
        (host_status, host_findings) where host_status is 'ok', 'warning', 'failed', 'ghost', or 'void'.
    """
    findings: list[str] = list(initial_findings or [])

    if open_port_count == 0:
        if was_ip_historically_active:
            if FINDING_HOST_GHOST not in findings:
                findings.append(FINDING_HOST_GHOST)
            return "ghost", findings
        else:
            return "void", findings

    has_open_failure = (
        any(s == "failed" for s in open_port_statuses) or has_error_port
    )
    has_open_warning = (
        any(s == "warning" for s in open_port_statuses) or has_ghost_port
    )

    if has_open_failure:
        host_status = "failed"
    elif has_open_warning:
        host_status = "warning"
    else:
        host_status = "ok"

    return host_status, findings
