from pydantic import BaseModel, ConfigDict, Field as PydanticField, model_serializer
from sqlmodel import Field, SQLModel, Column, JSON, Relationship
from typing import Literal

class Job(SQLModel, table=True):
    __tablename__: str = "jobs"  # type: ignore

    id: int | None = Field(default=None, primary_key=True)
    targets: list[str] = Field(sa_column=Column(JSON))
    ports: list[int] = Field(sa_column=Column(JSON))
    labels: dict[str, str] = Field(default_factory=dict, sa_column=Column(JSON))

class JobCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    targets: list[str]
    ports: list[int]
    labels: dict[str, str] = PydanticField(default_factory=dict)

class JobResponse(BaseModel):
    id: int

class HttpRoutingCheck(SQLModel, table=True):
    __tablename__: str = "http_routing_checks"  # type: ignore
    
    id: int | None = Field(default=None, primary_key=True)
    port_state_id: int = Field(foreign_key="port_states.id", exclude=True)
    
    domain: str
    status_code: int | None = None
    http_latency_ms: int | None = None
    path_checked: str = "/"
    redirects_to_url: str | None = None
    server_header: str | None = None
    notes: str | None = None

class TlsCertificate(SQLModel, table=True):
    __tablename__: str = "tls_certificates"  # type: ignore
    
    id: int | None = Field(default=None, primary_key=True)
    port_state_id: int = Field(foreign_key="port_states.id", exclude=True)
    
    valid: bool = False
    expires_in_days: int = 0
    issuer: str | None = None
    protocol_version: str | None = None
    domains_discovered_sans: list[str] = Field(default_factory=list, sa_column=Column(JSON))

class PortState(SQLModel, table=True):
    __tablename__: str = "port_states"  # type: ignore
    
    id: int | None = Field(default=None, primary_key=True)
    ip_state_id: int = Field(foreign_key="ip_states.id", exclude=True)
    
    port_number: int
    tcp_status: str = "closed"  # Keeping it as str to avoid SQLModel enum issues without passing sa_column
    tcp_latency_ms: int | None = None
    
    tls_certificate: TlsCertificate | None = Relationship(sa_relationship_kwargs={"lazy": "selectin"})
    http_routing_checks_list: list[HttpRoutingCheck] = Relationship(
        sa_relationship_kwargs={"cascade": "all, delete-orphan", "lazy": "selectin"}
    )

    @model_serializer(mode='wrap')
    def serialize_model(self, handler):
        res = handler(self)
        # Manually extract relationships since handler(self) excludes them by default
        res["http_routing_checks"] = {c.domain: c for c in self.http_routing_checks_list}
        if self.tls_certificate:
            res["tls_certificate"] = self.tls_certificate
        else:
            res["tls_certificate"] = None
        return res

class IpState(SQLModel, table=True):
    __tablename__: str = "ip_states"  # type: ignore
    
    id: int | None = Field(default=None, primary_key=True)
    job_id: int | None = Field(default=None, foreign_key="jobs.id")
    ip_address: str = Field(index=True)
    
    metadata_resolved_from: str | None = None
    metadata_discovered_from: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    
    ports_list: list[PortState] = Relationship(
        sa_relationship_kwargs={"cascade": "all, delete-orphan", "lazy": "selectin"}
    )

    @model_serializer(mode='wrap')
    def serialize_model(self, handler):
        res = handler(self)
        
        # Manually extract relationships
        res["ports"] = {str(p.port_number): p for p in self.ports_list}
        
        res["metadata"] = {
            "resolved_from": res.pop("metadata_resolved_from", None),
            "discovered_from": res.pop("metadata_discovered_from", [])
        }
        return res
