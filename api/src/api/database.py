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
