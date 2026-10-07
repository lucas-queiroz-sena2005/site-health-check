"""Command-line interface for the Site Health Check tool."""

import argparse
import json
import logging
import signal
import sys

from engine.parsing import expand_target_ranges, parse_ports, validate_and_clean_target
from engine.schemas.engine import TaskConfig, TaskFlags

logging.basicConfig(level=logging.WARNING, stream=sys.stderr, format="%(message)s")
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
    
    # Scoping Architecture
    parser.add_argument("--whitelist", type=str, default="", help="Comma-separated IP/CIDR/Domain whitelists")
    parser.add_argument("--blacklist", type=str, default="", help="Comma-separated IP/CIDR/Domain blacklists")
    
    parser.add_argument("-r", dest="follow_redirects", action="store_true", help="Follow Redirects (Strictly In-Scope)")
    parser.add_argument("-R", dest="follow_redirects_oos", action="store_true", help="Follow Redirects (Allow Out-of-Scope)")
    parser.add_argument("-s", dest="follow_sans", action="store_true", help="Discover SANs (Strictly In-Scope)")
    parser.add_argument("-S", dest="follow_sans_oos", action="store_true", help="Discover SANs (Allow Out-of-Scope)")
    parser.add_argument("-v", dest="force_vhost_origin", action="store_true", help="Force Vhost origin probing (DNS bypass)")
    
    parser.add_argument("--dr", type=int, default=3, help="Max hop depth for redirects")
    parser.add_argument("--ds", type=int, default=1, help="Max hop depth for SANs")
   
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
        "--debug", action="store_true", help="Enable verbose logging to stderr"
    )
    parser.add_argument(
        "--outfile", help="Save JSON results to specified file", default=None
    )
    parser.add_argument(
        "-o", "--output", choices=["json", "classic"], default="json", help="Output format for stdout (default: json)"
    )

    return parser


def main(args: list | None = None) -> int:
    """Main CLI entrypoint."""
    parser = build_parser()
    parsed_args = parser.parse_args(args)
    
    if parsed_args.debug:
        logging.getLogger().setLevel(logging.INFO)
        
    validation_result = validate_and_clean_target(parsed_args.target)
    if not validation_result.is_valid:
        logger.error(validation_result.error_message)
        return 1

    expanded_targets = expand_target_ranges(validation_result.segments)
    target_ports = parse_ports(parsed_args.ports)
  
    flags = TaskFlags(
        check_http=parsed_args.check_http,
        timeout_seconds=parsed_args.timeout,
        check_virtual_hosts=parsed_args.check_virtual_hosts,
        rate=parsed_args.rate,
        user_agent=parsed_args.user_agent,
        whitelist=parsed_args.whitelist,
        blacklist=parsed_args.blacklist,
        follow_redirects=parsed_args.follow_redirects,
        follow_redirects_out_of_scope=parsed_args.follow_redirects_oos,
        follow_sans=parsed_args.follow_sans,
        follow_sans_out_of_scope=parsed_args.follow_sans_oos,
        force_vhost_origin=parsed_args.force_vhost_origin,
        max_depth_redirects=parsed_args.dr,
        max_depth_sans=parsed_args.ds
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
        logger.warning(f"\n[!] Received signal {signum}, aborting engine...")
        cancel_engine()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    # --- The Engine Boundary ---
    run_engine(json_payload, workers_count=parsed_args.workers, output_format=parsed_args.output, outfile=parsed_args.outfile)

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
