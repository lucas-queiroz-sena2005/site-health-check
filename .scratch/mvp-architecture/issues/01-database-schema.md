---
labels: ["wayfinder:task", "status:closed"]
blocks: ["03-api-endpoints.md"]
---

# Decision Ticket: Database Schema Design

## Question

Given that we are using SQLite, cron for schedules, flexible classifications, and Jobs/Results (the "execution"), what are the exact tables, columns, and relationships we need to create for the MVP?

**Goal:** Produce the SQLite schema definitions (e.g., SQLAlchemy or raw SQL DDL) so development can begin.

## Resolution

The schema will be declared in Python using SQLAlchemy. This enables seamless `JSON` handling across SQLite and Postgres, and allows for clean object-relational mapping.

We have adopted a streamlined schema where scan settings are embedded in `Schedules`, linked via M:N to `Classifications` (which only store target strings). The `Job` table uses the **Immutable Snapshot** pattern to preserve the exact execution configuration. The results are fully normalized.

```python
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, Boolean, DateTime, ForeignKey, Table
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.dialects.sqlite import JSON

Base = declarative_base()

def generate_uuid():
    return str(uuid.uuid4())

# M:N Junction Table
schedule_classifications = Table(
    "schedule_classifications",
    Base.metadata,
    Column("schedule_id", String, ForeignKey("schedules.id"), primary_key=True),
    Column("classification_id", String, ForeignKey("classifications.id"), primary_key=True)
)

class Classification(Base):
    """A reusable, named grouping of targets."""
    __tablename__ = "classifications"
    id = Column(String, primary_key=True, default=generate_uuid)
    name = Column(String, nullable=False)
    # List of unexpanded target strings (e.g. ["example.com", "10.0.0.0/24"])
    targets_json = Column(JSON, nullable=False) 
    deleted_at = Column(DateTime, nullable=True) # Soft delete pattern

class Schedule(Base):
    """Defines when and how a scan occurs."""
    __tablename__ = "schedules"
    id = Column(String, primary_key=True, default=generate_uuid)
    name = Column(String, nullable=False)
    cron_expression = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    
    # Scan Settings
    ports_json = Column(JSON, nullable=False) # e.g. [80, 443, 8080]
    flags_json = Column(JSON, nullable=False) # The engine's TaskFlags (check_http, timeout, etc)
    
    deleted_at = Column(DateTime, nullable=True) # Soft delete pattern
    
    # M:N Relationship
    classifications = relationship("Classification", secondary=schedule_classifications)

class Job(Base):
    """A single execution instance of a Schedule."""
    __tablename__ = "jobs"
    id = Column(String, primary_key=True, default=generate_uuid)
    schedule_id = Column(String, ForeignKey("schedules.id"), nullable=True) # Null for on-demand
    
    # Immutable Snapshot: The exact unexpanded targets, ports, and flags at the time of execution.
    # Format: {"unexpanded_targets": [...], "ports": [...], "flags": {...}}
    execution_config_snapshot_json = Column(JSON, nullable=False)
    
    status = Column(String, nullable=False) # PENDING, RUNNING, COMPLETED, FAILED
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    metrics_json = Column(JSON, nullable=True) # Rollup metrics for History page

# --- Normalized Result Models ---

class IpState(Base):
    __tablename__ = "ip_states"
    id = Column(String, primary_key=True, default=generate_uuid)
    job_id = Column(String, ForeignKey("jobs.id"), nullable=False)
    ip_address = Column(String, nullable=False)
    metadata_resolved_from = Column(String, nullable=True)
    metadata_discovered_from_json = Column(JSON, nullable=False)

class PortState(Base):
    __tablename__ = "port_states"
    id = Column(String, primary_key=True, default=generate_uuid)
    ip_state_id = Column(String, ForeignKey("ip_states.id"), nullable=False)
    port_number = Column(Integer, nullable=False)
    tcp_status = Column(String, nullable=False)
    tcp_latency_ms = Column(Integer, nullable=True)

class TlsCertificate(Base):
    __tablename__ = "tls_certificates"
    id = Column(String, primary_key=True, default=generate_uuid)
    port_state_id = Column(String, ForeignKey("port_states.id"), nullable=False)
    valid = Column(Boolean, nullable=False)
    expires_in_days = Column(Integer, nullable=False)
    issuer = Column(String, nullable=True)
    protocol_version = Column(String, nullable=True)
    domains_discovered_sans_json = Column(JSON, nullable=False)

class HttpRoutingCheck(Base):
    __tablename__ = "http_routing_checks"
    id = Column(String, primary_key=True, default=generate_uuid)
    port_state_id = Column(String, ForeignKey("port_states.id"), nullable=False)
    domain = Column(String, nullable=False)
    status_code = Column(Integer, nullable=True)
    http_latency_ms = Column(Integer, nullable=True)
    path_checked = Column(String, nullable=False)
    redirects_to_url = Column(String, nullable=True)
    server_header = Column(String, nullable=True)
```
