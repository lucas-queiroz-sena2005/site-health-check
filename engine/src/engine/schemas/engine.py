import dataclasses
from typing import Any


@dataclasses.dataclass
class TaskFlags:
    """Configuration flags defining the depth and behavior of the scan."""
    check_http: bool = True
    timeout_seconds: int = 10
    recursive_san_check: bool = False
    check_virtual_hosts: bool = True
    out_of_scope_depth: int = 0
    rate: float = 50.0
    user_agent: str | None = None

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
class TaskContext:
    """The implicit lineage context of a discovery task."""
    flags: TaskFlags
    discovered_from: str | None = None
    parent_ip: str | None = None
    depth: int = 0


@dataclasses.dataclass
class EngineTask:
    """Internal task tracking for the engine queue."""
    target: str
    ports: list[int]
    context: TaskContext

    @classmethod
    def from_redirect_url(
        cls, 
        url: str, 
        context: TaskContext
    ) -> 'EngineTask':
        import yarl
        parsed = yarl.URL(url)
        target_domain = parsed.host
        if not target_domain:
            raise ValueError(f"No host found in URL: {url}")
        
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        return cls(
            target=target_domain,
            ports=[port],
            context=context
        )

@dataclasses.dataclass
class HttpRoutingCheck:
    """Represents the result of a specific HTTP test against a domain."""
    status_code: int | None = None
    http_latency_ms: int | None = None
    path_checked: str = "/"
    redirects_to_url: str | None = None
    server_header: str | None = None
    notes: str | None = None

@dataclasses.dataclass
class TlsCertificate:
    """Represents the parsed TLS certificate data."""
    valid: bool = False
    expires_in_days: int = 0
    issuer: str | None = None
    protocol_version: str | None = None
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
class IpMetadata:
    """Metadata detailing the origin of this IP state."""
    resolved_from: str | None = None
    discovered_from: list[str] = dataclasses.field(default_factory=list)

@dataclasses.dataclass
class IpState:
    """Represents the complete state of a single IP address."""
    metadata: IpMetadata = dataclasses.field(default_factory=IpMetadata)
    # Maps a Port Number (int) to its physical PortState
    ports: dict[int, PortState] = dataclasses.field(default_factory=dict)
