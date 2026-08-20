"""Strict data schemas for the Site Health Check engine."""

import dataclasses
from typing import Any


@dataclasses.dataclass
class TaskFlags:
    """Configuration flags defining the depth and behavior of the scan."""
    check_tcp: bool = True
    check_http: bool = True
    timeout_seconds: int = 10
    expected_strings: list[str] | None = None
    undesired_strings: list[str] | None = None
    recursive_san_check: bool = False
    check_virtual_hosts: bool = True
    out_of_scope_depth: int = 0

@dataclasses.dataclass
class TaskConfig:
    """
    Standardized payload format. 
    The core engine ONLY accepts lists of serialized TaskConfig dictionaries.
    """
    target: str
    ports: list[int]
    flags: TaskFlags
    discovered_from: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize object to the standardized JSON payload."""
        return dataclasses.asdict(self)

@dataclasses.dataclass
class HttpRoutingCheck:
    """Represents the result of a specific HTTP test against a domain."""
    status_code: int | None = None
    path_checked: str = "/"
    notes: str | None = None

@dataclasses.dataclass
class TlsCertificate:
    """Represents the parsed TLS certificate data."""
    valid: bool = False
    expires_in_days: int = 0
    issuer: str | None = None
    # A list of all SANs discovered on this certificate
    domains_discovered_sans: list[str] = dataclasses.field(default_factory=list)

@dataclasses.dataclass
class PortState:
    """Represents the physical reality of a single port on an IP."""
    tcp_status: str = "closed" # "open" or "closed"
    tcp_latency_ms: int | None = None
    tls_certificate: TlsCertificate | None = None
    
    # Maps a Domain Name (e.g., 'susy.ic.unicamp.br') to its HTTP routing result
    http_routing_checks: dict[str, HttpRoutingCheck] = dataclasses.field(default_factory=dict)

@dataclasses.dataclass
class IpState:
    """Represents the complete state of a single IP address."""
    metadata: dict[str, str] = dataclasses.field(default_factory=dict)
    # Maps a Port Number (int) to its physical PortState
    ports: dict[int, PortState] = dataclasses.field(default_factory=dict)

# The final results.json structure will simply be a dictionary mapping 
# an IP string to its serialized IpState:  Dict[str, IpState]
# Example:
# final_output = {
#     "143.106.10.50": dataclasses.asdict(my_ip_state_object)
# }
