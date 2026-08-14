"""Unit tests for site_health_check core logic."""

from site_health_check.cli import format_audit_summary
from site_health_check.core import is_valid_url, normalize_url, validate_html


class DummyResponse:
    def __init__(self, status_code=200, reason="OK", headers=None, text=""):
        self.status_code = status_code
        self.reason = reason
        self.headers = headers or {"Server": "nginx/1.18.0"}
        self.text = text


def test_is_valid_url_valid():
    assert is_valid_url("example.com") is True
    assert is_valid_url("https://example.com/api/health") is True
    assert is_valid_url("http://sub.domain.org:8080/test") is True
    assert is_valid_url("http://localhost:3000") is True
    assert is_valid_url("http://192.168.1.1:8000") is True


def test_is_valid_url_invalid():
    assert is_valid_url("not a url @@") is False
    assert is_valid_url("://bad.url") is False
    assert is_valid_url("") is False


def test_normalize_url():
    assert normalize_url("example.com") == "http://example.com"
    assert normalize_url("https://example.com") == "https://example.com"
    assert normalize_url("http://example.com") == "http://example.com"


def test_validate_html_expected_found():
    html = "<html><body><h1>Dashboard Active</h1></body></html>"
    passed, error = validate_html(html, "Dashboard Active", must_not_have=False)
    assert passed is True
    assert error is None


def test_validate_html_expected_missing():
    html = "<html><body><h1>Maintenance Mode</h1></body></html>"
    passed, error = validate_html(html, "Dashboard Active", must_not_have=False)
    assert passed is False
    assert "Expected string 'Dashboard Active' not found" in error


def test_validate_html_forbidden_found():
    html = "<html><body><h1>Internal Server Error 500</h1></body></html>"
    passed, error = validate_html(html, "Internal Server Error", must_not_have=True)
    assert passed is False
    assert "Forbidden string 'Internal Server Error' was found" in error


def test_validate_html_forbidden_not_found():
    html = "<html><body><h1>Service Healthy</h1></body></html>"
    passed, error = validate_html(html, "Internal Server Error", must_not_have=True)
    assert passed is True
    assert error is None


def test_format_audit_summary_success():
    res = DummyResponse(status_code=200, reason="OK", headers={"Server": "cloudflare"})
    summary = format_audit_summary("https://example.com", res)
    assert "URL: https://example.com | Server: cloudflare" in summary
    assert "Error Exception:" not in summary


def test_format_audit_summary_http_error():
    res = DummyResponse(
        status_code=404, reason="Not Found", headers={"Server": "nginx"}
    )
    summary = format_audit_summary("https://example.com", res)
    assert "URL: https://example.com | Server: nginx" in summary
    assert "Error Exception: HTTP 404 Not Found" in summary


def test_format_audit_summary_connection_error():
    summary = format_audit_summary(
        "https://invalid.domain",
        response=None,
        connection_error="Connection failed (Name or service not known)",
    )
    assert "URL: https://invalid.domain | Server: Unknown" in summary
    assert "Error Exception: Connection failed" in summary
