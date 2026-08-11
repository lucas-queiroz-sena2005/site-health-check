"""Command-line interface for the Site Health Check tool."""

import argparse
import sys
from typing import Optional
import requests

from site_health_check.core import is_valid_url, perform_check


def format_audit_summary(
    url: str,
    response: Optional[requests.Response],
    validation_error: Optional[str] = None,
    connection_error: Optional[str] = None,
) -> str:
    """Build a human-readable audit summary line."""
    if connection_error:
        return f"URL: {url} | Server: Unknown | Error Exception: {connection_error}"

    server = response.headers.get("Server", "Unknown") if response else "Unknown"
    status_line = f"HTTP {response.status_code} {response.reason}" if response else "No response"

    summary = f"URL: {url} | Server: {server}"

    # Handle HTTP Error Codes (4xx, 5xx)
    if response and response.status_code >= 400:
        summary += f" | Error Exception: {status_line}"

    # Handle HTML Payload Validation Errors
    if validation_error:
        if "Error Exception:" in summary:
            summary += f" | {validation_error}"
        else:
            summary += f" | Error Exception: {validation_error}"

    return summary


def build_parser() -> argparse.ArgumentParser:
    """Construct the command-line argument parser."""
    parser = argparse.ArgumentParser(
        prog="site-check",
        description="Web Health Auditor & Recon Tool",
    )
    parser.add_argument("url", help="Target URL (e.g., example.com)")
    parser.add_argument(
        "-s", "--string", help="String to validate in the HTML body", default=None
    )
    parser.add_argument(
        "--exclude",
        action="store_true",
        help="Fail if the string IS found (negative validation)",
    )
    parser.add_argument(
        "-t",
        "--timeout",
        type=int,
        default=10,
        help="Request timeout in seconds (default: 10)",
    )
    return parser


def main(args: Optional[list] = None) -> int:
    """Main CLI entrypoint."""
    parser = build_parser()
    parsed_args = parser.parse_args(args)
    target_url = parsed_args.url

    if not is_valid_url(target_url):
        print("Error: Invalid URL format.", file=sys.stderr)
        return 1

    response, validation_error, connection_error = perform_check(
        target_url=target_url,
        expected_string=parsed_args.string,
        must_not_have=parsed_args.exclude,
        timeout=parsed_args.timeout,
    )

    summary = format_audit_summary(
        url=target_url,
        response=response,
        validation_error=validation_error,
        connection_error=connection_error,
    )
    print(summary)

    if connection_error or (response and response.status_code >= 400) or validation_error:
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
