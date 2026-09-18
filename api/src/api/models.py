import uuid
from enum import Enum
from datetime import datetime, timezone
from pydantic import BaseModel, ConfigDict, Field as PydanticField, model_serializer
from sqlmodel import Field, SQLModel, Column, JSON, Relationship
from typing import Any

def generate_uuid() -> str:
    return str(uuid.uuid4())

class ScanRunStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

class ExecutionFlags(BaseModel):
    check_tcp: bool = PydanticField(
        default=True, title="Check TCP/TLS", 
        json_schema_extra={"cli_arg": "--check-tcp", "is_switch": True}
    )
    check_http: bool = PydanticField(
        default=True, title="Check HTTP Routing",
        json_schema_extra={"cli_arg": "--check-http", "is_switch": True}
    )
    recursive_san: bool = PydanticField(
        default=False, title="Recursive SAN Check",
        json_schema_extra={"cli_arg": "--recursive-san", "is_switch": True}
    )
    out_of_scope_depth: int = PydanticField(
        default=0, title="Out-of-Scope Depth",
        json_schema_extra={"cli_arg": "--out-of-scope-depth", "is_switch": False}
    )
    check_virtual_hosts: bool = PydanticField(
        default=True, title="Check Virtual Hosts",
        json_schema_extra={"cli_arg": "--check-virtual-hosts", "is_switch": True}
    )
    spoof_user_agent: bool = PydanticField(
        default=False, title="Spoof User Agent",
        json_schema_extra={"cli_arg": "--spoof-user-agent", "is_switch": True}
    )
    timeout: int = PydanticField(
        default=10, title="Timeout (seconds)",
        json_schema_extra={"cli_arg": "--timeout", "is_switch": False}
    )
    expected: list[str] | None = PydanticField(
        default=None, title="Expected HTML Strings",
        json_schema_extra={"cli_arg": "-e", "is_switch": False, "is_list": True}
    )
    undesired: list[str] | None = PydanticField(
        default=None, title="Undesired HTML Strings",
        json_schema_extra={"cli_arg": "-u", "is_switch": False, "is_list": True}
    )
    workers: int = PydanticField(
        default=100, title="Async Workers",
        json_schema_extra={"cli_arg": "-w", "is_switch": False}
    )
    delay: float = PydanticField(
        default=0.0, title="Worker Delay",
        json_schema_extra={"cli_arg": "--delay", "is_switch": False}
    )

class ExecutionConfig(BaseModel):
    targets: list[str] = PydanticField(default_factory=list, title="Targets")
    ports: list[str | int] = PydanticField(default_factory=list, title="Ports")
    flags: ExecutionFlags = PydanticField(default_factory=ExecutionFlags, title="Engine Flags")
    
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

class HostState(SQLModel, table=True):
    __tablename__: str = "host_states"  # type: ignore
    
    id: str = Field(default_factory=generate_uuid, primary_key=True)
    scan_run_id: str = Field(foreign_key="scan_runs.id")
    ip_address: str = Field(index=True)
    
    metadata_resolved_from: str | None = None
    metadata_discovered_from_json: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    
    ports_list: list[PortState] = Relationship(
        sa_relationship_kwargs={"cascade": "all, delete-orphan", "lazy": "selectin"}
    )

    @model_serializer(mode='wrap')
    def serialize_model(self, handler):
        res = handler(self)
        res["ports"] = {str(p.port_number): p for p in self.ports_list}
        res["metadata"] = {
            "resolved_from": res.pop("metadata_resolved_from", None),
            "discovered_from": res.pop("metadata_discovered_from_json", [])
        }
        return res

