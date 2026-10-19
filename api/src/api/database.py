import os
from collections.abc import Generator
from typing import Annotated

from fastapi import Depends
from sqlmodel import Session, create_engine

sqlite_url = os.environ.get("DATABASE_URL") or "sqlite:///site_health_check.db"

connect_args = {"check_same_thread": False} if sqlite_url.startswith("sqlite") else {}
engine = create_engine(sqlite_url, connect_args=connect_args)

def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session

SessionDep = Annotated[Session, Depends(get_session)]


def init_db() -> None:
    """Initializes tables and ensures schema migrations for SQLite."""
    from sqlalchemy import text
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
        except Exception:
            pass

