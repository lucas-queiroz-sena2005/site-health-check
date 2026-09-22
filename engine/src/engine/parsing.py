import ipaddress
import re
import sys
from collections.abc import Callable
from functools import wraps
from typing import Any

from engine.schemas.parsing import TargetSegment, TargetValidationResult

DOMAIN_REGEX = r"^([a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$|^localhost$"


def exit_on_error(func: Callable) -> Callable:
    """
    Decorator to catch ValueErrors and cleanly exit the CLI execution.
    This prevents messy stack traces from polluting the user's terminal.
    """
    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
    return wrapper


def normalize_url(url: str) -> str:
    """
    Ensures that a URL string has an 'http' or 'https' scheme.
    Defaults to 'https://' if none is provided.
    """
    if not url.startswith(("http://", "https://")):
        return f"https://{url}"
    return url


def _strip_scheme_and_validate_port(target: str) -> str:
    """
    Strips accidental HTTP/HTTPS schemes from targets and ensures they do not
    contain trailing ports, raising a ValueError if ports are detected.
    """
    cleaned = re.sub(r"^https?://", "", target.strip())
        
    if re.search(r":\d+(/|$)", cleaned):
        raise ValueError(f"Target string '{cleaned}' should not contain a port. Please use the -p / --ports argument instead.")
            
    # Strip trailing paths for domains (e.g., example.com/api -> example.com)
    # We check if the base part (before any '/') is a valid domain.
    base_target = cleaned.split("/")[0]
    if bool(re.match(DOMAIN_REGEX, base_target)):
        return base_target
            
    return cleaned


def _categorize_segment(cleaned: str) -> TargetSegment:
    """
    Categorizes a cleaned segment string natively using the ipaddress library.
    Identifies if a string is a domain, a raw IP, an IP range, or a CIDR block.
    """
    # 1. Domain (e.g., "example.com")
    if bool(re.match(DOMAIN_REGEX, cleaned)):
        return TargetSegment(segment_type="domain", data=cleaned, suffix=None)

    # 2. Hyphenated IP bounds (e.g., "10.0.0.5-10.0.0.8" or "10.0.0.5/24-10.0.0.8/24")
    if "-" in cleaned:
        try:
            start_str, end_str = cleaned.split("-")
            
            # Natively validate the base IP addresses
            start_ip = ipaddress.IPv4Address(start_str.split("/")[0])
            end_ip = ipaddress.IPv4Address(end_str.split("/")[0])
            
            if "/" in cleaned:
                suffix = start_str.split("/")[1]
                return TargetSegment(segment_type="cidr", data=f"{start_ip}-{end_ip}", suffix=f"/{suffix}")
            
            return TargetSegment(segment_type="ip", data=cleaned, suffix=None)
        except (ValueError, IndexError):
            pass

    # 3. Single CIDR block or Single IP (e.g., "10.0.0.0/24" or "10.0.0.5")
    try:
        network = ipaddress.IPv4Network(cleaned, strict=False)
        if "/" in cleaned:
            return TargetSegment(segment_type="cidr", data=str(network.network_address), suffix=f"/{network.prefixlen}")
        return TargetSegment(segment_type="ip", data=cleaned, suffix=None)
    except ValueError:
        pass

    raise ValueError(f"'{cleaned}' is not a valid Domain, IPv4 address, or CIDR block.")


def validate_and_clean_target(target: str) -> TargetValidationResult:
    """
    Validates a target string (comma-separated), strips accidental schemes,
    and cleanly categorizes them into segments.
    """
    segments = []
    parts = target.split(",")
    for part in parts:
        if not part.strip():
            continue
        try:
            cleaned = _strip_scheme_and_validate_port(part)
            segment = _categorize_segment(cleaned)
            segments.append(segment)
        except ValueError as e:
            return TargetValidationResult(is_valid=False, error_message=str(e), segments=[])
            
    if not segments:
        return TargetValidationResult(is_valid=False, error_message="Error: No valid targets provided.", segments=[])
        
    return TargetValidationResult(is_valid=True, error_message="Valid targets", segments=segments)


def expand_range(start_val: str, end_val: str | None, range_type: str) -> list[str | int]:
    """
    Universal range expansion function. 
    Expands hyphenated string ranges into fully enumerated lists based on their type.
    """
    if range_type == "port":
        start, end = int(start_val), int(str(end_val))
        if start > end:
            raise ValueError(f"Range start ({start}) cannot be > end ({end})")
        return [port for port in range(start, end + 1) if 0 < port <= 65535]
    
    elif range_type == "ip":
        try:
            start_ip = int(ipaddress.IPv4Address(start_val))
            end_ip = int(ipaddress.IPv4Address(str(end_val)))
            if start_ip > end_ip:
                raise ValueError(f"Range start ({start_val}) cannot be > end ({end_val})")
            return [str(ipaddress.IPv4Address(ip)) for ip in range(start_ip, end_ip + 1)]
        except ValueError as e:
            raise ValueError(f"Invalid IP range: {e}")
            
    elif range_type == "cidr":
        try:
            if end_val:
                # CIDR range logic: Iterate within the network bounds of the suffix
                suffix = start_val.split("/")[-1]
                start_ip = ipaddress.IPv4Address(start_val.split("/")[0])
                end_ip = ipaddress.IPv4Address(end_val.split("/")[0])
                
                if start_ip > end_ip:
                    raise ValueError(f"Range start ({start_val}) cannot be > end ({end_val})")

                # Reconstruct the network block based on the start IP and suffix
                network = ipaddress.IPv4Network(f"{start_ip}/{suffix}", strict=False)
                results = []

                for ip in network:
                    if ip < start_ip:
                        continue
                    if ip > end_ip:
                        break
                    results.append(str(ip))
                return results
            else:
                # Single CIDR block generation
                network = ipaddress.IPv4Network(start_val, strict=False)
                return [str(ip) for ip in network.hosts()]
        except ValueError as e:
            raise ValueError(f"Invalid CIDR block or range: {e}")
            
    raise ValueError(f"Unknown range type: {range_type}")


def expand_target_ranges(segments: list[TargetSegment]) -> list[str]:
    """
    Expands segments into a flat list of raw IPs and Domains.
    Note: The final list MUST NOT contain CIDR suffixes.
    """
    final_targets = []
    for seg in segments:
        if seg.segment_type == "domain":
            final_targets.append(seg.data)
        elif seg.segment_type == "ip":
            if "-" in seg.data:
                start, end = seg.data.split("-")
                # mypy workaround: expand_range returns list[str | int]
                final_targets.extend(str(t) for t in expand_range(start, end, "ip"))
            else:
                final_targets.append(seg.data)
        elif seg.segment_type == "cidr":
            if "-" in seg.data:
                start, end = seg.data.split("-")
                final_targets.extend(str(t) for t in expand_range(f"{start}{seg.suffix}", f"{end}{seg.suffix}", "cidr"))
            else:
                final_targets.extend(str(t) for t in expand_range(f"{seg.data}{seg.suffix}", None, "cidr"))
    return final_targets


@exit_on_error
def parse_ports(ports_arg: int | str = 80) -> list[int]:
    """Parses port arguments (ints, CSVs, or ranges) into a valid list of ports."""
    if isinstance(ports_arg, int):
        if 0 < ports_arg <= 65535:
            return [ports_arg]
        raise ValueError(f"Port {ports_arg} is out of valid range (1-65535)")

    target_ports = []
    for part in str(ports_arg).replace(" ", "").split(","):
        if not part:
            continue
        if "-" in part:
            numbers = part.split("-")
            if len(numbers) != 2:
                raise ValueError(f"Invalid range format in '{part}'")
            ports_in_range = expand_range(numbers[0], numbers[1], "port")
            if not ports_in_range:
                raise ValueError(f"No valid ports found in range '{part}'")
            target_ports.extend(int(p) for p in ports_in_range)
        else:
            port = int(part)
            if 0 < port <= 65535:
                target_ports.append(port)
            else:
                raise ValueError(f"Port {port} out of valid range (1-65535)")

    return sorted(set(target_ports))
