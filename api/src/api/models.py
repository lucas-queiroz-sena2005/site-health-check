import uuid
from enum import Enum
from datetime import datetime, timezone
from pydantic import BaseModel, ConfigDict, Field as PydanticField, model_serializer
from sqlmodel import Field, SQLModel, Column, JSON, Relationship
from typing import Any

def generate_uuid() -> str:
    return str(uuid.uuid4())

class JobStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

class ExecutionConfig(BaseModel):
    targets: list[str] = PydanticField(default_factory=list, title="Targets")
    ports: list[int] = PydanticField(default_factory=list, title="Ports")
    check_http: bool = PydanticField(default=True, title="Check HTTP Routing")
    timeout_seconds: int = PydanticField(default=30, title="Timeout (seconds)")
    # Additional flags can be added here easily
    
class ScheduleClassificationLink(SQLModel, table=True):
    __tablename__: str = "schedule_classifications"  # type: ignore
    schedule_id: str = Field(foreign_key="schedules.id", primary_key=True)
    classification_id: str = Field(foreign_key="classifications.id", primary_key=True)

class Classification(SQLModel, table=True):
    __tablename__: str = "classifications"  # type: ignore
    id: str = Field(default_factory=generate_uuid, primary_key=True)
    name: str
    targets_json: list[str] = Field(sa_column=Column(JSON))
    deleted_at: datetime | None = None
    
    schedules: list["Schedule"] = Relationship(back_populates="classifications", link_model=ScheduleClassificationLink)

class Schedule(SQLModel, table=True):
    __tablename__: str = "schedules"  # type: ignore
    id: str = Field(default_factory=generate_uuid, primary_key=True)
    name: str
    cron_expression: str
    is_active: bool = True
    
    ports_json: list[int] = Field(sa_column=Column(JSON))
    flags_json: dict[str, Any] = Field(sa_column=Column(JSON))
    
    deleted_at: datetime | None = None
    
    classifications: list[Classification] = Relationship(back_populates="schedules", link_model=ScheduleClassificationLink)

class Job(SQLModel, table=True):
    __tablename__: str = "jobs"  # type: ignore
    id: str = Field(default_factory=generate_uuid, primary_key=True)
    schedule_id: str | None = Field(default=None, foreign_key="schedules.id")
    
    # Snapshot of what was requested
    execution_config_snapshot_json: dict[str, Any] = Field(sa_column=Column(JSON))
    
    status: JobStatus = Field(default=JobStatus.PENDING)
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
    ip_state_id: str = Field(foreign_key="ip_states.id", exclude=True)
    
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

class IpState(SQLModel, table=True):
    __tablename__: str = "ip_states"  # type: ignore
    
    id: str = Field(default_factory=generate_uuid, primary_key=True)
    job_id: str = Field(foreign_key="jobs.id")
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

