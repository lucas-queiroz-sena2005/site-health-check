"""Command-line interface for the Site Health Check tool."""

import argparse
import json
import logging
import signal
import sys

from engine.parsing import expand_target_ranges, parse_ports, validate_and_clean_target
from engine.schemas.engine import TaskConfig, TaskFlags

logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(message)s")
logger = logging.getLogger(__name__)

def build_parser() -> argparse.ArgumentParser:
    """Construct the command-line argument parser."""
    parser = argparse.ArgumentParser(
        prog="site-check",
        description="Web Health Auditor & Network Prober",
    )
    parser.add_argument(
        "target", help="Target Host or URL (e.g., example.com or 192.168.1.50)"
    )

    parser.add_argument(
        "-p", "--ports", default="443", help="Target port(s) (e.g., 443, 8000-8050)"
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
        "--check-virtual-hosts",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Check HTTP responses for all discovered Virtual Hosts on the same IP",
    )
    parser.add_argument(
        "--user-agent",
        type=str,
        default=None,
        help="Override the standard User-Agent for requests",
    )
    parser.add_argument(
        "-t",
        "--timeout",
        type=int,
        default=10,
        help="Request timeout in seconds (default: 10)",
    )

    # Engine Execution & Tuning Arguments
    parser.add_argument(
        "-w",
        "--workers",
        type=int,
        default=100,
        help="Number of concurrent asynchronous workers (default: 100)",
    )
    parser.add_argument(
        "--rate",
        type=float,
        default=50.0,
        help="Global rate limit for connections/requests per second (default: 50.0)",
    )
    
    # Observability & Output
    parser.add_argument(
        "-o", "--output", help="Save results to specified JSON file (legacy, ignored)", default=None
    )

    return parser


def main(args: list | None = None) -> int:
    """Main CLI entrypoint."""
    parser = build_parser()
    parsed_args = parser.parse_args(args)
    validation_result = validate_and_clean_target(parsed_args.target)
    if not validation_result.is_valid:
        logger.error(validation_result.error_message)
        return 1

    expanded_targets = expand_target_ranges(validation_result.segments)
    target_ports = parse_ports(parsed_args.ports)
  
    flags = TaskFlags(
        check_http=parsed_args.check_http,
        timeout_seconds=parsed_args.timeout,
        recursive_san_check=parsed_args.recursive_san,
        check_virtual_hosts=parsed_args.check_virtual_hosts,
        out_of_scope_depth=parsed_args.out_of_scope_depth,
        rate=parsed_args.rate,
        user_agent=parsed_args.user_agent
    )
    
    json_payload = []
    for t in expanded_targets:
        task = TaskConfig(
            target=t,
            ports=target_ports,
            flags=flags
        )
        json_payload.append(task.to_dict())
    
    logger.info("\n[*] Standardized Payload Built:")
    logger.info(json.dumps(json_payload, indent=2))
    logger.info("\n[*] Handing off to Core Engine...")
    
    from engine.engine import cancel_engine, run_engine
    
    aborted = False
    
    def handle_signal(signum, frame):
        nonlocal aborted
        if aborted:
            return
        aborted = True
        logger.info(f"\n[!] Received signal {signum}, aborting engine...")
        cancel_engine()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    # --- The Engine Boundary ---
    run_engine(json_payload, workers_count=parsed_args.workers)

    if aborted:
        sys.stdout.write(json.dumps({"status": "aborted", "reason": "signal"}) + "\n")
        sys.stdout.flush()
        return 130 # standard exit code for SIGINT (128+2)
    else:
        sys.stdout.write(json.dumps({"status": "completed"}) + "\n")
        sys.stdout.flush()
        logger.info("\n[+] Scan Complete.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
