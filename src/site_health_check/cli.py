"""Command-line interface for the Site Health Check tool."""

import argparse
import json
import sys

from site_health_check.parsing import is_valid_url, parse_ports
from site_health_check.schema import TaskConfig, TaskFlags


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
    parser.add_argument(
        "-r",
        "--recursive-san",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Recursively queue and scan discovered SANs from TLS certificates",
    )
    parser.add_argument(
        "--out-of-scope-depth",
        type=int,
        default=0,
        help="Depth of out-of-scope (different IP) recursive SAN resolution. 0 = strict same-IP only.",
    )
   
    # HTTP Check Arguments
    parser.add_argument(
        "--check-http",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Run HTTP payload validation",
    )
    parser.add_argument(
        "-e", "--expected", action="append", help="Expected string(s) to validate in the HTML body"
    )
    parser.add_argument(
        "-u", "--undesired", action="append", help="Undesired string(s) to fail if found"
    )
    parser.add_argument(
        "--check-virtual-hosts",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Check HTTP responses for all discovered Virtual Hosts on the same IP",
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
  
    flags = TaskFlags(
        check_tcp=parsed_args.check_tcp,
        check_http=parsed_args.check_http,
        timeout_seconds=parsed_args.timeout,
        expected_strings=parsed_args.expected,
        undesired_strings=parsed_args.undesired,
        recursive_san_check=parsed_args.recursive_san,
        check_virtual_hosts=parsed_args.check_virtual_hosts,
        out_of_scope_depth=parsed_args.out_of_scope_depth
    )
    
    task = TaskConfig(
        target=target,
        ports=target_ports,
        flags=flags
    )
    
    # Serialize to the universal JSON payload format
    json_payload = [task.to_dict()]
    
    print("\n[*] Standardized Payload Built:")
    print(json.dumps(json_payload, indent=2))
    print("\n[*] Handing off to Core Engine...")
    
    # --- The Engine Boundary ---
    from site_health_check.engine import run_engine
    results = run_engine(json_payload)

    # Unified Terminal Output
    print("\n[+] Scan Complete. Output State:")
    print(json.dumps(results, indent=2))

    # State Export
    if parsed_args.output and results:
        from site_health_check.exporter import export_results
        saved_path = export_results(results, parsed_args.output)
        print(f"\n[+] Results saved to {saved_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
