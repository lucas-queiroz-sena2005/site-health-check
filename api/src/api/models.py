import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, model_serializer
from pydantic import Field as PydanticField
from sqlmodel import JSON, Column, Field, Relationship, SQLModel, UniqueConstraint


def generate_uuid() -> str:
    return str(uuid.uuid4())

class ScanRunStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    ABORTED = "ABORTED"

from engine.schemas.engine import ExecutionFlags, TaskFlags

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
    
class ScanTargetGroupLink(SQLModel, table=True):
    __tablename__: str = "scan_target_groups"  # type: ignore
    scan_id: str = Field(foreign_key="scans.id", primary_key=True)
    target_group_id: str = Field(foreign_key="target_groups.id", primary_key=True)

class TargetGroup(SQLModel, table=True):
    __tablename__: str = "target_groups"  # type: ignore
    id: str = Field(default_factory=generate_uuid, primary_key=True)
    name: str
    is_ad_hoc: bool = False
    targets_json: list[str] = Field(sa_column=Column(JSON))
    deleted_at: datetime | None = None
    
    scans: list["Scan"] = Relationship(back_populates="target_groups", link_model=ScanTargetGroupLink)

class Scan(SQLModel, table=True):
    __tablename__: str = "scans"  # type: ignore
    id: str = Field(default_factory=generate_uuid, primary_key=True)
    name: str
    cron_expression: str | None = None
    is_active: bool = True
    
    ports_json: list[str | int] = Field(sa_column=Column(JSON))
    flags_json: dict[str, Any] = Field(sa_column=Column(JSON))
    ghost_window: str = Field(default="7d")
    tls_warning_days: int = Field(default=30)
    alert_config_json: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    alerts_muted: bool = Field(default=False)
    
    deleted_at: datetime | None = None
    
    target_groups: list[TargetGroup] = Relationship(back_populates="scans", link_model=ScanTargetGroupLink)

class ScanRun(SQLModel, table=True):
    __tablename__: str = "scan_runs"  # type: ignore
    id: str = Field(default_factory=generate_uuid, primary_key=True)
    scan_id: str | None = Field(default=None, foreign_key="scans.id")
    
    # Snapshot of what was requested
    execution_config_snapshot_json: dict[str, Any] = Field(sa_column=Column(JSON))
    
    status: ScanRunStatus = Field(default=ScanRunStatus.PENDING)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    metrics_json: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))

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
    port_state_id: str = Field(foreign_key="port_states.id", exclude=True)
    
    domain: str
    status_code: int | None = None
    http_latency_ms: int | None = None
    path_checked: str = "/"
    redirects_to_url: str | None = None
    server_header: str | None = None
    notes: str | None = None

class TlsCertificate(SQLModel, table=True):
    __tablename__: str = "tls_certificates"  # type: ignore
    
    id: str = Field(default_factory=generate_uuid, primary_key=True)
    port_state_id: str = Field(foreign_key="port_states.id", exclude=True)
    
    valid: bool = False
    expires_in_days: int = 0
    issuer: str | None = None
    protocol_version: str | None = None
    domains_discovered_sans_json: list[str] = Field(default_factory=list, sa_column=Column(JSON))

class PortState(SQLModel, table=True):
    __tablename__: str = "port_states"  # type: ignore
    __table_args__ = (UniqueConstraint("host_state_id", "port_number"),)
    
    id: str = Field(default_factory=generate_uuid, primary_key=True)
    host_state_id: str = Field(foreign_key="host_states.id", exclude=True)
    
    port_number: int
    tcp_status: str = "closed"
    tcp_latency_ms: int | None = None
    
    tls_certificate: TlsCertificate | None = Relationship(sa_relationship_kwargs={"lazy": "selectin"})
    http_routing_checks_list: list[HttpRoutingCheck] = Relationship(
        sa_relationship_kwargs={"cascade": "all, delete-orphan", "lazy": "selectin"}
    )

    @model_serializer(mode='wrap')
    def serialize_model(self, handler):
        res = handler(self)
        res["http_routing_checks"] = {c.domain: c for c in self.http_routing_checks_list}
        if self.tls_certificate:
            res["tls_certificate"] = self.tls_certificate
        else:
            res["tls_certificate"] = None
        return res

    @property
    def http_routing_checks(self) -> list[HttpRoutingCheck]:
        return self.http_routing_checks_list

class HostState(SQLModel, table=True):
    __tablename__: str = "host_states"  # type: ignore
    __table_args__ = (UniqueConstraint("scan_run_id", "ip_address"),)
    
    id: str = Field(default_factory=generate_uuid, primary_key=True)
    scan_run_id: str = Field(foreign_key="scan_runs.id")
    ip_address: str = Field(index=True)
    subrun_id: str | None = Field(default=None, index=True)
    
    metadata_resolved_from: str | None = None
    metadata_discovered_from_json: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    
    ports_list: list[PortState] = Relationship(
        sa_relationship_kwargs={"cascade": "all, delete-orphan", "lazy": "selectin"}
    )

    @property
    def ports(self) -> list[PortState]:
        return self.ports_list

    @model_serializer(mode='wrap')
    def serialize_model(self, handler):
        res = handler(self)
        res["ports"] = {str(p.port_number): p for p in self.ports_list}
        res["metadata"] = {
            "resolved_from": res.pop("metadata_resolved_from", None),
            "discovered_from": res.pop("metadata_discovered_from_json", [])
        }
        return res

