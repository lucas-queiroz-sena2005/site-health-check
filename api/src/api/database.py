import os
import sqlite3
from collections.abc import Generator
from typing import Annotated

from fastapi import Depends
from sqlalchemy import event, text
from sqlalchemy.engine import Engine
from sqlmodel import Session, create_engine

sqlite_url = os.environ.get("DATABASE_URL") or "sqlite:///site_health_check.db"

connect_args = {"check_same_thread": False} if sqlite_url.startswith("sqlite") else {}
engine = create_engine(sqlite_url, connect_args=connect_args)

@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON;")
        cursor.execute("PRAGMA busy_timeout=5000;")
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA synchronous=NORMAL;")
        cursor.close()


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session

SessionDep = Annotated[Session, Depends(get_session)]


def init_db() -> None:
    """Initializes tables and ensures schema migrations for SQLite."""
    from enum import Enum
    from sqlalchemy import inspect
    from sqlmodel import SQLModel

    try:
        SQLModel.metadata.create_all(engine)
        with engine.begin() as conn:
            inspector = inspect(conn)
            existing_tables = set(inspector.get_table_names())

            for table_name, table in SQLModel.metadata.tables.items():
                if table_name not in existing_tables:
                    continue

                existing_cols = {col["name"] for col in inspector.get_columns(table_name)}
                for col in table.columns:
                    if col.name in existing_cols:
                        continue

                    type_str = col.type.compile(conn.dialect)
                    default_clause = ""
                    if col.default is not None and hasattr(col.default, "arg"):
                        val = col.default.arg
                        if isinstance(val, Enum):
                            val = val.value
                        if isinstance(val, bool):
                            default_clause = f" DEFAULT {1 if val else 0}"
                        elif isinstance(val, (int, float)):
                            default_clause = f" DEFAULT {val}"
                        elif isinstance(val, str):
                            escaped = val.replace("'", "''")
                            default_clause = f" DEFAULT '{escaped}'"
                    elif type_str.upper() == "JSON":
                        default_clause = " DEFAULT '[]'"
                    elif not col.nullable:
                        if "INT" in type_str.upper():
                            default_clause = " DEFAULT 0"
                        elif "BOOL" in type_str.upper():
                            default_clause = " DEFAULT 0"
                        else:
                            default_clause = " DEFAULT ''"

                    conn.execute(
                        text(f'ALTER TABLE "{table_name}" ADD COLUMN "{col.name}" {type_str}{default_clause}')
                    )

        from api.models import SystemConfig
        with Session(engine) as session:
            cfg = session.get(SystemConfig, 1)
            if not cfg:
                session.add(SystemConfig(id=1, retention_days=0))
                session.commit()
    except Exception as exc:
        raise RuntimeError(f"Database initialization/migration failed: {exc}") from exc
