"""Parsing utilities for the Site Health Check tool."""

import re
import sys


def is_valid_url(url: str) -> bool:
    """Validate whether the provided string matches a valid URL/domain pattern."""
    regex = (
        r"^(https?://)?"
        r"(([a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}|localhost|\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"
        r"(:\d{1,5})?"
        r"(/[-a-zA-Z0-9@:%_\+.~#?&//=]*)?$"
    )
    return bool(re.match(regex, url))


def normalize_url(url: str) -> str:
    """Ensure URL has an http or https scheme. Defaults to https."""
    if not url.startswith(("http://", "https://")):
        return f"https://{url}"
    return url


def parse_ports(ports_arg: int | str = 80) -> list[int]:
    """Parses port arguments (ints, CSVs, or ranges) into a valid list of ports."""
    if isinstance(ports_arg, int):
        if 0 < ports_arg <= 65535:
            return [ports_arg]
        print(f"Error: Port {ports_arg} is out of valid range (1-65535)")
        sys.exit(1)

    target_ports = []
    for part in str(ports_arg).replace(" ", "").split(","):
        if not part:
            continue
        try:
            if "-" in part:
                numbers = part.split("-")
                if len(numbers) != 2:
                    raise ValueError(f"Invalid range format in '{part}'")
                start, end = int(numbers[0]), int(numbers[1])
                if start > end:
                    raise ValueError(f"Range start ({start}) cannot be > end ({end})")

                for port in range(start, end + 1):
                    if 0 < port <= 65535:
                        target_ports.append(port)
                    else:
                        raise ValueError(f"Port {port} out of valid range (1-65535)")
            else:
                port = int(part)
                if 0 < port <= 65535:
                    target_ports.append(port)
                else:
                    raise ValueError(f"Port {port} out of valid range (1-65535)")

        except ValueError as e:
            print(f"Error parsing port argument: {e}", file=sys.stderr)
            sys.exit(1)

    return sorted(list(set(target_ports)))
