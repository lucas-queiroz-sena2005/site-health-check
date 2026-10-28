import dataclasses
from typing import Any
from pydantic import BaseModel, Field, AliasChoices


class TaskFlags(BaseModel):
    """Configuration flags defining the depth and behavior of the scan."""
    check_http: bool = Field(default=True, title="Check HTTP Routing")
    recursive_san: bool = Field(
        default=False,
        title="Recursive SAN Check",
        validation_alias=AliasChoices("recursive_san", "recursive_san_check"),
    )
    out_of_scope_depth: int = Field(default=0, title="Out-of-Scope Depth")
    check_virtual_hosts: bool = Field(default=True, title="Check Virtual Hosts")
    timeout: int = Field(
        default=10,
        title="Timeout (seconds)",
        validation_alias=AliasChoices("timeout", "timeout_seconds"),
    )
    workers: int = Field(default=100, title="Async Workers")
    rate: float = Field(default=50.0, title="Rate Limit (req/s)")
    user_agent: str | None = Field(default=None, title="Custom User Agent")

    @property
    def timeout_seconds(self) -> int:
        return self.timeout

    @property
    def recursive_san_check(self) -> bool:
        return self.recursive_san


ExecutionFlags = TaskFlags


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
        return {
            "target": self.target,
            "ports": list(self.ports),
            "flags": self.flags.model_dump() if hasattr(self.flags, "model_dump") else self.flags,
            "discovered_from": self.discovered_from,
        }


@dataclasses.dataclass
class TaskContext:
    """The implicit lineage context of a discovery task."""
    flags: TaskFlags
    discovered_from: str | None = None
    parent_ip: str | None = None
    depth: int = 0
    subrun_id: str | None = None
    root_target: str | None = None


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
    subrun_id: str | None = None
    root_target: str | None = None

@dataclasses.dataclass
class IpState:
    """Represents the complete state of a single IP address."""
    metadata: IpMetadata = dataclasses.field(default_factory=IpMetadata)
    # Maps a Port Number (int) to its physical PortState
    ports: dict[int, PortState] = dataclasses.field(default_factory=dict)
