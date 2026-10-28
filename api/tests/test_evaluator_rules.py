import pytest
from api.services.evaluator_rules import (
    FINDING_HTTP_4XX,
    FINDING_HTTP_5XX,
    FINDING_HTTP_ERROR,
    FINDING_HOST_GHOST,
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


def test_evaluate_http_check():
    # 2xx / 3xx -> ok, None
    assert evaluate_http_check(200) == ("ok", None)
    assert evaluate_http_check(204) == ("ok", None)
    assert evaluate_http_check(301) == ("ok", None)
    assert evaluate_http_check(302) == ("ok", None)

    # 4xx -> warning, HTTP_4XX
    assert evaluate_http_check(400) == ("warning", FINDING_HTTP_4XX)
    assert evaluate_http_check(403) == ("warning", FINDING_HTTP_4XX)
    assert evaluate_http_check(404) == ("warning", FINDING_HTTP_4XX)

    # 5xx -> failed, HTTP_5XX
    assert evaluate_http_check(500) == ("failed", FINDING_HTTP_5XX)
    assert evaluate_http_check(502) == ("failed", FINDING_HTTP_5XX)
    assert evaluate_http_check(503) == ("failed", FINDING_HTTP_5XX)

    # None / connection failure -> failed, HTTP_ERROR
    assert evaluate_http_check(None) == ("failed", FINDING_HTTP_ERROR)


def test_is_deprecated_tls():
    assert is_deprecated_tls("SSLv2") is True
    assert is_deprecated_tls("SSLv3") is True
    assert is_deprecated_tls("TLSv1") is True
    assert is_deprecated_tls("TLSv1.0") is True
    assert is_deprecated_tls("TLSv1.1") is True
    assert is_deprecated_tls("TLSv1.2") is False
    assert is_deprecated_tls("TLSv1.3") is False
    assert is_deprecated_tls(None) is False
    assert is_deprecated_tls("") is False


def test_evaluate_tls_cert():
    # Invalid certificate
    findings, min_days = evaluate_tls_cert(valid=False, expires_in_days=30, protocol_version="TLSv1.3", tls_warning_days=30)
    assert FINDING_TLS_INVALID in findings
    assert min_days is None

    # Expired certificate (valid=True but expires_in_days <= 0)
    findings, min_days = evaluate_tls_cert(valid=True, expires_in_days=0, protocol_version="TLSv1.3", tls_warning_days=30)
    assert FINDING_TLS_EXPIRED in findings
    assert min_days is None

    findings, min_days = evaluate_tls_cert(valid=True, expires_in_days=-5, protocol_version="TLSv1.3", tls_warning_days=30)
    assert FINDING_TLS_EXPIRED in findings
    assert min_days is None

    # Expiring soon within threshold (e.g. 15 <= 30)
    findings, min_days = evaluate_tls_cert(valid=True, expires_in_days=15, protocol_version="TLSv1.3", tls_warning_days=30)
    assert FINDING_TLS_EXPIRING_SOON in findings
    assert min_days == 15

    # Healthy TLS (expires in 90 days > 30)
    findings, min_days = evaluate_tls_cert(valid=True, expires_in_days=90, protocol_version="TLSv1.3", tls_warning_days=30)
    assert findings == []
    assert min_days == 90

    # Deprecated TLS version added to findings
    findings, min_days = evaluate_tls_cert(valid=True, expires_in_days=90, protocol_version="TLSv1.0", tls_warning_days=30)
    assert FINDING_TLS_DEPRECATED_VERSION in findings
    assert min_days == 90


def test_evaluate_port():
    # 1. Routine closed void port
    status, findings, is_ghost = evaluate_port(
        tcp_status="closed",
        check_statuses=[],
        check_findings=[],
        tls_findings=[],
        was_historically_open=False,
    )
    assert status == "void"
    assert FINDING_TCP_CLOSED in findings
    assert is_ghost is False

    # 2. Historically active closed port -> ghost port
    status, findings, is_ghost = evaluate_port(
        tcp_status="closed",
        check_statuses=[],
        check_findings=[],
        tls_findings=[],
        was_historically_open=True,
    )
    assert status == "ghost"
    assert FINDING_TCP_CLOSED in findings
    assert FINDING_HOST_GHOST in findings
    assert is_ghost is True

    # 3. Open port with healthy checks
    status, findings, is_ghost = evaluate_port(
        tcp_status="open",
        check_statuses=["ok"],
        check_findings=[],
        tls_findings=[],
        was_historically_open=False,
    )
    assert status == "ok"
    assert is_ghost is False

    # 4. Open port with 4xx warning
    status, findings, is_ghost = evaluate_port(
        tcp_status="open",
        check_statuses=["warning"],
        check_findings=[FINDING_HTTP_4XX],
        tls_findings=[],
        was_historically_open=False,
    )
    assert status == "warning"
    assert FINDING_HTTP_4XX in findings

    # 5. Open port with TLS expiring soon warning
    status, findings, is_ghost = evaluate_port(
        tcp_status="open",
        check_statuses=["ok"],
        check_findings=[],
        tls_findings=[FINDING_TLS_EXPIRING_SOON],
        was_historically_open=False,
    )
    assert status == "warning"
    assert FINDING_TLS_EXPIRING_SOON in findings

    # 6. Open port with 5xx failure
    status, findings, is_ghost = evaluate_port(
        tcp_status="open",
        check_statuses=["failed"],
        check_findings=[FINDING_HTTP_5XX],
        tls_findings=[],
        was_historically_open=False,
    )
    assert status == "failed"
    assert FINDING_HTTP_5XX in findings

    # 7. Open port with invalid TLS failure
    status, findings, is_ghost = evaluate_port(
        tcp_status="open",
        check_statuses=["ok"],
        check_findings=[],
        tls_findings=[FINDING_TLS_INVALID],
        was_historically_open=False,
    )
    assert status == "failed"
    assert FINDING_TLS_INVALID in findings


def test_evaluate_host_status():
    # 0 open ports, not historically active -> void
    status, findings = evaluate_host_status(
        open_port_count=0,
        open_port_statuses=[],
        has_error_port=False,
        has_ghost_port=False,
        was_ip_historically_active=False,
    )
    assert status == "void"
    assert findings == []

    # 0 open ports, historically active -> ghost
    status, findings = evaluate_host_status(
        open_port_count=0,
        open_port_statuses=[],
        has_error_port=False,
        has_ghost_port=False,
        was_ip_historically_active=True,
    )
    assert status == "ghost"
    assert FINDING_HOST_GHOST in findings

    # Open ports all ok -> ok
    status, findings = evaluate_host_status(
        open_port_count=2,
        open_port_statuses=["ok", "ok"],
        has_error_port=False,
        has_ghost_port=False,
        was_ip_historically_active=False,
    )
    assert status == "ok"

    # Open ports with warning -> warning
    status, findings = evaluate_host_status(
        open_port_count=2,
        open_port_statuses=["ok", "warning"],
        has_error_port=False,
        has_ghost_port=False,
        was_ip_historically_active=False,
    )
    assert status == "warning"

    # Open ports all ok BUT has a closed ghost port on the host -> warning
    status, findings = evaluate_host_status(
        open_port_count=1,
        open_port_statuses=["ok"],
        has_error_port=False,
        has_ghost_port=True,
        was_ip_historically_active=False,
    )
    assert status == "warning"

    # Open ports with failed port -> failed
    status, findings = evaluate_host_status(
        open_port_count=2,
        open_port_statuses=["ok", "failed"],
        has_error_port=False,
        has_ghost_port=False,
        was_ip_historically_active=False,
    )
    assert status == "failed"

    # Open ports with error tcp -> failed
    status, findings = evaluate_host_status(
        open_port_count=1,
        open_port_statuses=["ok"],
        has_error_port=True,
        has_ghost_port=False,
        was_ip_historically_active=False,
    )
    assert status == "failed"
