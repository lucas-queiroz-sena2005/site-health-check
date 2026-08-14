"""Command-line interface for the Site Health Check tool."""

import argparse
import json
import sys

from site_health_check.core import scan_target
from site_health_check.parsing import is_valid_url, parse_ports


def build_parser() -> argparse.ArgumentParser:
    """Construct the command-line argument parser."""
    parser = argparse.ArgumentParser(
        prog="site-check",
        description="Web Health Auditor & Network Prober",
    )
    parser.add_argument(
        "target", help="Target Host or URL (e.g., example.com or 192.168.1.50)"
    )

    # Network Prober Arguments
    parser.add_argument(
        "-p", "--ports", default="443", help="Target port(s) (e.g., 443, 8000-8050)"
    )
    parser.add_argument(
        "--check-tcp",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Run TCP/TLS port scan",
    )

    # HTTP Check Arguments
    parser.add_argument(
        "--check-http",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Run HTTP payload validation",
    )
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

    # Observability & Output
    parser.add_argument(
        "--push-url", help="Optional Webhook URL for observability tools"
    )
    parser.add_argument(
        "-o", "--output", help="Save results to specified JSON file", default=None
    )

    return parser


def main(args: list | None = None) -> int:
    """Main CLI entrypoint."""
    parser = build_parser()
    parsed_args = parser.parse_args(args)
    target = parsed_args.target

    if not is_valid_url(target):
        print(f"Error: Invalid target format: {target}", file=sys.stderr)
        return 1

    target_ports = parse_ports(parsed_args.ports)
    
    print(f"\n[*] Starting Scan on {target}...")
    results = scan_target(
        target=target,
        target_ports=target_ports,
        check_tcp=parsed_args.check_tcp,
        check_http=parsed_args.check_http,
        expected_string=parsed_args.string,
        must_not_have=parsed_args.exclude,
        timeout=parsed_args.timeout,
    )

    # Unified Terminal Output
    for port, res in results["ports"].items():
        print(f"\n  -> Port {port}:")
        
        # TCP/TLS Output
        if parsed_args.check_tcp:
            print(f"     [NET] TCP: {res.get('tcp_status', 'N/A')} | TLS: {res.get('tls_status', 'N/A')}")
            if res.get("error"):
                print(f"           Error: {res['error']}")
            elif res.get("tls_details"):
                print(f"           Expires in: {res['tls_details']['days_left']} days")
                
        # HTTP Output
        if parsed_args.check_http and res.get("http"):
            http_res = res["http"]
            status_line = (
                f"HTTP {http_res['status_code']} {http_res['reason']}"
                if http_res.get('status_code')
                else "No response"
            )
            print(f"     [WEB] {status_line} ({http_res['url_tested']})")
            if http_res.get("validation_error"):
                print(f"           Validation Error: {http_res['validation_error']}")
            if http_res.get("connection_error"):
                print(f"           Connection Error: {http_res['connection_error']}")

    # 4. State Export
    if parsed_args.output and results:
        with open(parsed_args.output, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\n[+] Port scan results saved to {parsed_args.output}")

    # Webhook push logic omitted for now as requested

    return 0


if __name__ == "__main__":
    sys.exit(main())
