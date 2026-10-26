import ipaddress
import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from engine.schemas.engine import ExecutionFlags, TaskFlags
from pydantic import BaseModel
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

class AlertConfig(BaseModel):
    webhook_url: str | None = PydanticField(default=None, title="Webhook URL")
    alert_on_failure: bool = PydanticField(default=True, title="Alert on Failures")
    alert_on_ghost: bool = PydanticField(default=True, title="Alert on Ghost Hosts")
    alert_on_warning: bool = PydanticField(default=True, title="Alert on Warnings")
    alert_on_abort: bool = PydanticField(default=True, title="Alert on Run Abort/Crash")
    alert_on_void: bool = PydanticField(default=False, title="Alert on Void Hosts")
    notify_on_healthy: bool = PydanticField(default=False, title="Notify on Healthy Runs")

class ExecutionConfig(BaseModel):
    targets: list[str] = PydanticField(default_factory=list, title="Targets")
    ports: list[str | int] = PydanticField(default_factory=list, title="Ports")
    flags: ExecutionFlags = PydanticField(default_factory=ExecutionFlags, title="Engine Flags")
    ghost_window: str = PydanticField(default="7d", title="Ghost Window")
    tls_warning_days: int = PydanticField(default=30, title="TLS Expiry Warning Threshold (days)")
    prune_void_hosts: bool = PydanticField(default=True, title="Prune Void Hosts on Finalization")
    prune_closed_ports: bool = PydanticField(default=True, title="Prune Routine Closed Ports on Finalization")

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
