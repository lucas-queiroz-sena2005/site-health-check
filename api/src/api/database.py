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
            res = conn.execute(text("PRAGMA table_info(scans)"))
            existing_cols = {row[1] for row in res.fetchall()}
            if existing_cols and "alerts_muted" not in existing_cols:
                conn.execute(
                    text("ALTER TABLE scans ADD COLUMN alerts_muted BOOLEAN DEFAULT 0")
                )
            if existing_cols and "targets" not in existing_cols:
                conn.execute(
                    text("ALTER TABLE scans ADD COLUMN targets JSON DEFAULT '[]'")
                )
                try:
                    # Optional data migration if old target_groups tables exist
                    rows = conn.execute(text("""
                        SELECT s.id, tg.targets_json
                        FROM scans s
                        JOIN scan_target_groups stg ON s.id = stg.scan_id
                        JOIN target_groups tg ON stg.target_group_id = tg.id
                    """)).fetchall()
                    for scan_id, targets_json in rows:
                        conn.execute(
                            text("UPDATE scans SET targets = :targets WHERE id = :id"),
                            {"targets": targets_json, "id": scan_id},
                        )
                except Exception:
                    pass
        except Exception:
            pass
