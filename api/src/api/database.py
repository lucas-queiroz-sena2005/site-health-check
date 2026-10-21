import os
from collections.abc import Generator
from typing import Annotated

from fastapi import Depends
from sqlalchemy import event, text
from sqlmodel import Session, create_engine

sqlite_url = os.environ.get("DATABASE_URL") or "sqlite:///site_health_check.db"

connect_args = {"check_same_thread": False} if sqlite_url.startswith("sqlite") else {}
engine = create_engine(sqlite_url, connect_args=connect_args)

if sqlite_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON;")
        cursor.execute("PRAGMA busy_timeout=5000;")
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.close()


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session

SessionDep = Annotated[Session, Depends(get_session)]


def init_db() -> None:
    """Initializes tables and ensures schema migrations for SQLite."""
    from sqlmodel import SQLModel

    SQLModel.metadata.create_all(engine)
    with engine.begin() as conn:
        try:
            # 1. Scans migrations
            res = conn.execute(text("PRAGMA table_info(scans)"))
            existing_cols = {row[1] for row in res.fetchall()}
            if existing_cols:
                if "alerts_muted" not in existing_cols:
                    conn.execute(
                        text("ALTER TABLE scans ADD COLUMN alerts_muted BOOLEAN DEFAULT 0")
                    )
                if "targets" not in existing_cols:
                    conn.execute(
                        text("ALTER TABLE scans ADD COLUMN targets JSON DEFAULT '[]'")
                    )

            # 2. HostState migrations (Track 2: set-union lineage + evaluation columns)
            res = conn.execute(text("PRAGMA table_info(host_states)"))
            host_cols = {row[1] for row in res.fetchall()}
            if host_cols:
                new_host_cols = {
                    "resolved_domains": "JSON DEFAULT '[]'",
                    "discovered_from": "JSON DEFAULT '[]'",
                    "depth": "INTEGER DEFAULT 0",
                    "status": "VARCHAR DEFAULT 'ok'",
                    "open_port_count": "INTEGER DEFAULT 0",
                    "scanned_port_count": "INTEGER DEFAULT 0",
                    "vhost_count": "INTEGER DEFAULT 0",
                    "min_tcp_latency_ms": "INTEGER DEFAULT NULL",
                    "min_tls_expires_days": "INTEGER DEFAULT NULL",
                    "worst_tls_version": "VARCHAR DEFAULT NULL",
                    "worst_http_status": "INTEGER DEFAULT NULL",
                    "finding_codes": "JSON DEFAULT '[]'",
                }
                for col_name, col_def in new_host_cols.items():
                    if col_name not in host_cols:
                        conn.execute(text(f"ALTER TABLE host_states ADD COLUMN {col_name} {col_def}"))

            # 3. PortState migrations (Track 2: evaluation columns)
            res = conn.execute(text("PRAGMA table_info(port_states)"))
            port_cols = {row[1] for row in res.fetchall()}
            if port_cols:
                new_port_cols = {
                    "status": "VARCHAR DEFAULT 'ok'",
                    "san_count": "INTEGER DEFAULT 0",
                    "http_check_count": "INTEGER DEFAULT 0",
                    "worst_http_status": "INTEGER DEFAULT NULL",
                    "finding_codes": "JSON DEFAULT '[]'",
                }
                for col_name, col_def in new_port_cols.items():
                    if col_name not in port_cols:
                        conn.execute(text(f"ALTER TABLE port_states ADD COLUMN {col_name} {col_def}"))

            # 4. HttpRoutingCheck migrations (Track 2: evaluation columns)
            res = conn.execute(text("PRAGMA table_info(http_routing_checks)"))
            check_cols = {row[1] for row in res.fetchall()}
            if check_cols:
                new_check_cols = {
                    "status": "VARCHAR DEFAULT 'ok'",
                    "finding_code": "VARCHAR DEFAULT NULL",
                }
                for col_name, col_def in new_check_cols.items():
                    if col_name not in check_cols:
                        conn.execute(text(f"ALTER TABLE http_routing_checks ADD COLUMN {col_name} {col_def}"))

        except Exception:
            pass
