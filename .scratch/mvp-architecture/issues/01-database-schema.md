---
labels: ["wayfinder:task", "status:closed"]
blocks: ["03-api-endpoints.md"]
---

# Decision Ticket: Database Schema Design

## Question

Given that we are using SQLite, cron for schedules, flexible classifications, and have Policies (the "how"), Classifications (the "who"), and Jobs/Results (the "execution"), what are the exact tables, columns, and relationships we need to create for the MVP?

**Goal:** Produce the SQLite schema definitions (e.g., SQLAlchemy or raw SQL DDL) so development can begin.

## Resolution

The schema will be declared in Python using SQLAlchemy. This enables seamless `JSON` handling across SQLite and Postgres, and allows for clean object-relational mapping.

We have adopted Option 1 (Junction Tables) and standard governance patterns: **Immutable Snapshots**, **Soft Deletes**, and **Blast Radius Limits**.

```python
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, Boolean, DateTime, ForeignKey, Table
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.dialects.sqlite import JSON

Base = declarative_base()

def generate_uuid():
    return str(uuid.uuid4())

# Option 1: Many-to-Many Junction Tables
schedule_policies = Table(
    "schedule_policies",
    Base.metadata,
    Column("schedule_id", String, ForeignKey("schedules.id"), primary_key=True),
    Column("policy_id", String, ForeignKey("policies.id"), primary_key=True)
)

schedule_classifications = Table(
    "schedule_classifications",
    Base.metadata,
    Column("schedule_id", String, ForeignKey("schedules.id"), primary_key=True),
    Column("classification_id", String, ForeignKey("classifications.id"), primary_key=True)
)

class Policy(Base):
    __tablename__ = "policies"
    id = Column(String, primary_key=True, default=generate_uuid)
    name = Column(String, nullable=False)
    config_json = Column(JSON, nullable=False)  # SQLAlchemy handles TEXT <-> JSON automatically
    max_targets_allowed = Column(Integer, default=1000) # Blast radius limit
    deleted_at = Column(DateTime, nullable=True) # Soft delete pattern

class Classification(Base):
    __tablename__ = "classifications"
    id = Column(String, primary_key=True, default=generate_uuid)
    name = Column(String, nullable=False)
    targets_json = Column(JSON, nullable=False)
    labels_json = Column(JSON, nullable=True)
    deleted_at = Column(DateTime, nullable=True) # Soft delete pattern

class Schedule(Base):
    __tablename__ = "schedules"
    id = Column(String, primary_key=True, default=generate_uuid)
    name = Column(String, nullable=False)
    cron_expression = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    deleted_at = Column(DateTime, nullable=True) # Soft delete pattern
    
    # M:N Relationships back to Policies and Classifications
    policies = relationship("Policy", secondary=schedule_policies)
    classifications = relationship("Classification", secondary=schedule_classifications)

class Job(Base):
    """Execution instance. Represents a single run of a Policy against a Classification."""
    __tablename__ = "jobs"
    id = Column(String, primary_key=True, default=generate_uuid)
    schedule_id = Column(String, ForeignKey("schedules.id"), nullable=True) # NULL means 'On-Demand Scan'
    
    # Immutable Snapshots (Governance Pattern A)
    policy_snapshot_json = Column(JSON, nullable=False)
    targets_snapshot_json = Column(JSON, nullable=False)
    
    status = Column(String, nullable=False) # PENDING, RUNNING, COMPLETED, FAILED
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    metrics_json = Column(JSON, nullable=True) # Rollup metrics (total, green, red, duration) for History page

class Result(Base):
    __tablename__ = "results"
    id = Column(String, primary_key=True, default=generate_uuid)
    job_id = Column(String, ForeignKey("jobs.id"), nullable=False)
    ip = Column(String, nullable=False)
    ip_state_json = Column(JSON, nullable=False)
    discovered_from = Column(String, nullable=True)
```
