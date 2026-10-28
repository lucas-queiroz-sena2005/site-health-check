import ipaddress
import re
import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from engine.parsing import validate_and_clean_target
from engine.schemas.engine import ExecutionFlags, TaskFlags
from pydantic import BaseModel, field_validator
from pydantic import Field as PydanticField
from sqlmodel import JSON, Column, Field, Relationship, SQLModel, UniqueConstraint


def generate_uuid() -> str:
    return str(uuid.uuid4())


class EntityStatus(str, Enum):
    OK = "ok"
    WARNING = "warning"
    FAILED = "failed"
    GHOST = "ghost"
    VOID = "void"


def compute_ip_sort_key(ip: str | None) -> str | None:
    """Computes a database-agnostic, 32-character hex sort key for IPv4 and IPv6 addresses."""
    if not ip:
        return None
    try:
        ip_obj = ipaddress.ip_address(str(ip).strip())
        if ip_obj.version == 4:
            return f"00000000000000000000ffff{int(ip_obj):08x}"
        return f"{int(ip_obj):032x}"
    except (ValueError, TypeError, AttributeError):
        return None


class ScanRunStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    ABORTED = "ABORTED"

def sanitize_and_validate_targets(targets: list[str]) -> list[str]:
    """Cleans and validates each target string using engine.parsing without breaking CIDR or ranges."""
    cleaned_targets: list[str] = []
    for raw in targets:
        if not isinstance(raw, str):
            raise ValueError("Target must be a string")
        stripped = raw.strip()
        if not stripped:
            continue
        res = validate_and_clean_target(stripped)
        if not res.is_valid:
            raise ValueError(res.error_message)
        for seg in res.segments:
            cleaned_targets.append(f"{seg.data}{seg.suffix}" if seg.suffix else seg.data)
    return cleaned_targets


def sanitize_and_validate_ports(ports: list[str | int]) -> list[str | int]:
    """Validates integer ports and hyphenated port ranges (1-65535) without calling sys.exit."""
    cleaned_ports: list[str | int] = []
    for item in ports:
        if isinstance(item, int) and not isinstance(item, bool):
            if 1 <= item <= 65535:
                cleaned_ports.append(item)
            else:
                raise ValueError(f"Port {item} is out of valid range (1-65535)")
        elif isinstance(item, str):
            for part in item.split(","):
                p = part.strip()
                if not p:
                    continue
                if "-" in p:
                    bounds = p.split("-")
                    if len(bounds) != 2 or not bounds[0].isdigit() or not bounds[1].isdigit():
                        raise ValueError(
                            f"Invalid port range '{p}' (expected 'start-end' between 1 and 65535)"
                        )
                    start_p, end_p = int(bounds[0]), int(bounds[1])
                    if not (1 <= start_p <= end_p <= 65535):
                        raise ValueError(
                            f"Invalid port range '{p}' (start must be <= end and between 1 and 65535)"
                        )
                    cleaned_ports.append(f"{start_p}-{end_p}")
                elif p.isdigit():
                    p_int = int(p)
                    if not (1 <= p_int <= 65535):
                        raise ValueError(f"Port {p_int} is out of valid range (1-65535)")
                    cleaned_ports.append(p_int)
                else:
                    raise ValueError(
                        f"Invalid port '{p}' (must be an integer between 1 and 65535 or a range like '8080-8090')"
                    )
        else:
            raise ValueError(f"Invalid port value: {item}")
    return cleaned_ports


class AlertConfig(BaseModel):
    webhook_url: str | None = PydanticField(default=None, title="Webhook URL")
    alert_on_failure: bool = PydanticField(default=True, title="Alert on Failures")
    alert_on_ghost: bool = PydanticField(default=True, title="Alert on Ghost Hosts")
    alert_on_warning: bool = PydanticField(default=True, title="Alert on Warnings")
    alert_on_abort: bool = PydanticField(default=True, title="Alert on Run Abort/Crash")
    alert_on_void: bool = PydanticField(default=False, title="Alert on Void Hosts")
    notify_on_healthy: bool = PydanticField(default=False, title="Notify on Healthy Runs")

    @field_validator("webhook_url", mode="before")
    @classmethod
    def validate_webhook_url(cls, v: Any) -> str | None:
        if v is None:
            return None
        if isinstance(v, str):
            cleaned = v.strip()
            if not cleaned:
                return None
            if not (cleaned.startswith("http://") or cleaned.startswith("https://")):
                raise ValueError("Webhook URL must start with http:// or https://")
            return cleaned
        raise ValueError("Webhook URL must be a string")


class ExecutionConfig(BaseModel):
    targets: list[str] = PydanticField(
        default_factory=list,
        title="Targets",
        examples=[["example.com", "192.168.1.0/24"]],
    )
    ports: list[str | int] = PydanticField(
        default_factory=list,
        title="Ports",
        examples=[[80, 443]],
    )
    flags: ExecutionFlags = PydanticField(default_factory=ExecutionFlags, title="Engine Flags")
    ghost_window: str = PydanticField(default="7d", title="Ghost Window")
    tls_warning_days: int = PydanticField(
        default=30, ge=0, le=3650, title="TLS Expiry Warning Threshold (days)"
    )
    prune_void_hosts: bool = PydanticField(default=True, title="Prune Void Hosts on Finalization")
    prune_closed_ports: bool = PydanticField(default=True, title="Prune Routine Closed Ports on Finalization")

    @field_validator("targets")
    @classmethod
    def validate_targets_list(cls, v: list[str]) -> list[str]:
        return sanitize_and_validate_targets(v)

    @field_validator("ports")
    @classmethod
    def validate_ports_list(cls, v: list[str | int]) -> list[str | int]:
        return sanitize_and_validate_ports(v)

    @field_validator("ghost_window")
    @classmethod
    def validate_ghost_window(cls, v: str) -> str:
        cleaned = v.strip().lower()
        if not re.fullmatch(r"^\d+[smhd]$", cleaned):
            raise ValueError(
                "Ghost window must be a positive number followed by s, m, h, or d (e.g. '7d', '24h', '30m')"
            )
        return cleaned

class Scan(SQLModel, table=True):
    __tablename__: str = "scans"  # type: ignore
    id: str = Field(default_factory=generate_uuid, primary_key=True)
    name: str
    cron_expression: str | None = None
    is_active: bool = True
    
    targets: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    ports_json: list[str | int] = Field(sa_column=Column(JSON))
    flags_json: dict[str, Any] = Field(sa_column=Column(JSON))
    ghost_window: str = Field(default="7d")
    tls_warning_days: int = Field(default=30)
    alert_config_json: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    alerts_muted: bool = Field(default=False)
    
    deleted_at: datetime | None = None

class ScanRun(SQLModel, table=True):
    __tablename__: str = "scan_runs"  # type: ignore
    id: str = Field(default_factory=generate_uuid, primary_key=True)
    scan_id: str | None = Field(default=None, foreign_key="scans.id", ondelete="CASCADE")
    
    # Snapshot of what was requested
    execution_config_snapshot_json: dict[str, Any] = Field(sa_column=Column(JSON))
    
    status: ScanRunStatus = Field(default=ScanRunStatus.PENDING)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    metrics_json: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))

    hosts: list["HostState"] = Relationship(
        sa_relationship_kwargs={"cascade": "all, delete-orphan", "lazy": "selectin"}
    )

class SavedView(SQLModel, table=True):
    __tablename__: str = "saved_views"  # type: ignore
    id: str = Field(default_factory=generate_uuid, primary_key=True)
    name: str
    search: str | None = None
    statuses: list[str] | None = Field(default=None, sa_column=Column(JSON))
    table_sort_by: str | None = None
    table_sort_dir: str | None = None

class HttpRoutingCheck(SQLModel, table=True):
    __tablename__: str = "http_routing_checks"  # type: ignore
    __table_args__ = (UniqueConstraint("port_state_id", "domain"),)
    
    id: str = Field(default_factory=generate_uuid, primary_key=True)
    port_state_id: str = Field(foreign_key="port_states.id", ondelete="CASCADE", exclude=True)
    
    domain: str
    status_code: int | None = None
    http_latency_ms: int | None = None
    path_checked: str = "/"
    redirects_to_url: str | None = None
    server_header: str | None = None
    notes: str | None = None

    status: str = Field(default="ok")  # ok | warning | failed
    finding_code: str | None = None

class TlsCertificate(SQLModel, table=True):
    __tablename__: str = "tls_certificates"  # type: ignore
    __table_args__ = (UniqueConstraint("port_state_id"),)
    
    id: str = Field(default_factory=generate_uuid, primary_key=True)
    port_state_id: str = Field(foreign_key="port_states.id", ondelete="CASCADE", exclude=True)
    
    valid: bool = False
    expires_in_days: int = 0
    issuer: str | None = None
    protocol_version: str | None = None
    domains_discovered_sans_json: list[str] = Field(default_factory=list, sa_column=Column(JSON))

class PortState(SQLModel, table=True):
    __tablename__: str = "port_states"  # type: ignore
    __table_args__ = (UniqueConstraint("host_state_id", "port_number"),)
    
    id: str = Field(default_factory=generate_uuid, primary_key=True)
    host_state_id: str = Field(foreign_key="host_states.id", ondelete="CASCADE", exclude=True)
    
    port_number: int
    tcp_status: str = "closed"
    tcp_latency_ms: int | None = None

    status: str = Field(default="ok")  # ok | warning | failed
    san_count: int = Field(default=0)
    http_check_count: int = Field(default=0)
    worst_http_status: int | None = None
    finding_codes: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    
    tls_certificate: TlsCertificate | None = Relationship(
        sa_relationship_kwargs={"cascade": "all, delete-orphan", "lazy": "selectin"}
    )
    http_routing_checks: list[HttpRoutingCheck] = Relationship(
        sa_relationship_kwargs={"cascade": "all, delete-orphan", "lazy": "selectin"}
    )

class HostState(SQLModel, table=True):
    __tablename__: str = "host_states"  # type: ignore
    __table_args__ = (UniqueConstraint("scan_run_id", "ip_address"),)
    
    id: str = Field(default_factory=generate_uuid, primary_key=True)
    scan_run_id: str = Field(foreign_key="scan_runs.id", ondelete="CASCADE")
    ip_address: str = Field(index=True)
    ip_sort_key: str | None = Field(default=None, index=True)
    subrun_id: str | None = Field(default=None, index=True)
    
    resolved_domains: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    discovered_from: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    depth: int = Field(default=0)

    status: str = Field(default="ok")  # ok | warning | failed | ghost
    open_port_count: int = Field(default=0)
    scanned_port_count: int = Field(default=0)
    vhost_count: int = Field(default=0)
    min_tcp_latency_ms: int | None = None
    min_tls_expires_days: int | None = None
    worst_tls_version: str | None = None
    worst_http_status: int | None = None
    finding_codes: list[str] = Field(default_factory=list, sa_column=Column(JSON))

    def model_post_init(self, __context: Any) -> None:
        super().model_post_init(__context)
        if self.ip_sort_key is None and self.ip_address:
            self.ip_sort_key = compute_ip_sort_key(self.ip_address)
        if self.depth == 0 and self.discovered_from:
            filtered = [d for d in self.discovered_from if d != self.ip_address]
            if filtered:
                self.depth = len(filtered)
        if self.vhost_count == 0 and self.resolved_domains:
            self.vhost_count = len(self.resolved_domains)
    
    ports: list[PortState] = Relationship(
        sa_relationship_kwargs={"cascade": "all, delete-orphan", "lazy": "selectin"}
    )
