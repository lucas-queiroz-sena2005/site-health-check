"""Core validation and auditing logic for web health checks."""

import re
import socket
import ssl
import time
from datetime import datetime
from typing import Any

import requests

from site_health_check.catcher import validate_html
from site_health_check.parsing import normalize_url


def check_tcp_and_tls(host: str, port: int, timeout: float = 2.0) -> dict[str, Any]:
    """
    Performs a TCP handshake and attempts a TLS handshake.
    Returns a standardized dictionary representing the state of the port.
    """
    response = {
        "host": host,
        "port": port,
        "tcp_status": "DOWN",  # "UP" or "DOWN"
        "tcp_latency_ms": None,
        "tls_status": "NONE",  # "NONE", "VALID", or "INVALID"
        "tls_details": None,  # Dictionary of cert details if VALID
        "error": None,  # Human-readable error string if something failed
    }

    context = ssl.create_default_context()
    start_time = time.perf_counter()

    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            response["tcp_status"] = "UP"
            response["tcp_latency_ms"] = round(
                (time.perf_counter() - start_time) * 1000, 2
            )
            try:
                with context.wrap_socket(sock, server_hostname=host) as ssock:
                    response["tls_status"] = "VALID"
                    # Extract raw data
                    cert = ssock.getpeercert()
                    protocol, cipher, _ = ssock.cipher()
                    # Parse Issuer
                    issuer_data = dict(x[0] for x in cert.get("issuer", []))
                    issuer_name = issuer_data.get("organizationName", "Unknown")
                    # Parse Expiration
                    expire_date = datetime.strptime(
                        cert["notAfter"], "%b %d %H:%M:%S %Y %Z"
                    )
                    days_left = (expire_date - datetime.utcnow()).days

                    # Populate standardized TLS details
                    response["tls_details"] = {
                        "issuer": issuer_name,
                        "days_left": days_left,
                        "expires_on": expire_date.isoformat(),
                        "protocol": protocol,
                        "cipher": cipher,
                    }

            except ssl.SSLError as tls_err:
                response["tls_status"] = "INVALID"
                response["error"] = f"TLS Error: {tls_err}"

    except TimeoutError:
        response["error"] = "Network Error: Connection timed out"
    except ConnectionRefusedError:
        response["error"] = "Network Error: Connection refused by server"
    except Exception as e:
        response["error"] = f"Unexpected Error: {e}"

    return response


def perform_check(
    target_url: str,
    expected_strings: list[str] | None = None,
    undesired_strings: list[str] | None = None,
    timeout: int = 10,
) -> tuple[requests.Response | None, str | None, str | None]:
    """
    Perform HTTP request and HTML validation.
    Returns (response, validation_error, connection_error).
    """
    normalized_url = normalize_url(target_url)
    try:
        response = requests.get(normalized_url, timeout=timeout, allow_redirects=True)
    except requests.RequestException as e:
        return None, None, f"Connection failed ({e})"

    validation_error = None
    if expected_strings or undesired_strings:
        passed, msg = validate_html(
            response.text, 
            expected_strings=expected_strings, 
            undesired_strings=undesired_strings
        )
        if not passed:
            validation_error = msg

    return response, validation_error, None


def scan_target(
    target: str,
    target_ports: list[int],
    check_tcp: bool = True,
    check_http: bool = True,
    expected_strings: list[str] | None = None,
    undesired_strings: list[str] | None = None,
    timeout: int = 10,
) -> dict[str, Any]:
    """
    Executes a complete scan against a target, unifying TCP and HTTP results per port.
    Can be imported and used programmatically without the CLI.
    """
    results: dict[str, Any] = {"target": target, "ports": {}}

    for port in target_ports:
        port_data = {}
        
        # 1. Network / TLS Check
        if check_tcp:
            port_data = check_tcp_and_tls(target, port, timeout=2.0)
        else:
            port_data = {"tcp_status": "SKIPPED", "tls_status": "SKIPPED"}
            
        # 2. HTTP Check
        if check_http and port_data.get("tcp_status") != "DOWN":
            # Smart Protocol Detection
            protocol = "https" if port_data.get("tls_status") == "VALID" else "http"
            url = f"{protocol}://{target}:{port}"
            
            response, val_err, conn_err = perform_check(
                target_url=url,
                expected_strings=expected_strings,
                undesired_strings=undesired_strings,
                timeout=timeout,
            )
            
            port_data["http"] = {
                "url_tested": url,
                "status_code": response.status_code if response else None,
                "reason": response.reason if response else None,
                "validation_error": val_err,
                "connection_error": conn_err,
            }
        else:
            port_data["http"] = None
            
        results["ports"][port] = port_data

    return results
