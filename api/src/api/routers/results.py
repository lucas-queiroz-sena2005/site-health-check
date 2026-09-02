from typing import Annotated

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from api.database import get_session
from api.models import IpState

router = APIRouter(prefix="/results", tags=["results"])

SessionDep = Annotated[Session, Depends(get_session)]

@router.get("")
def get_results(session: SessionDep) -> list[IpState]:
    statement = select(IpState)
    results = session.exec(statement).all()
    return list(results)
