from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel, ConfigDict
from sqlmodel import Session

from api.database import get_session
from api.models import SavedView

router = APIRouter(prefix="/views", tags=["views"])

SessionDep = Annotated[Session, Depends(get_session)]

class SavedViewCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    search: str | None = None
    statuses: list[str] | None = None
    table_sort_by: str | None = None
    table_sort_dir: str | None = None

class SavedViewResponse(SavedViewCreate):
    id: str
    model_config = ConfigDict(from_attributes=True)

@router.post("", status_code=status.HTTP_201_CREATED)
def create_view(view_in: SavedViewCreate, session: SessionDep) -> SavedViewResponse:
    db_view = SavedView(**view_in.model_dump())
    session.add(db_view)
    session.commit()
    session.refresh(db_view)
    
    return SavedViewResponse.model_validate(db_view)

@router.get("/{id}")
def get_view(id: Annotated[str, Path()], session: SessionDep) -> SavedViewResponse:
    db_view = session.get(SavedView, id)
    if not db_view:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="View not found"
        )
    
    return SavedViewResponse.model_validate(db_view)

@router.get("")
def list_views(session: SessionDep) -> list[SavedViewResponse]:
    from sqlmodel import select
    stmt = select(SavedView)
    views = session.exec(stmt).all()
    return [SavedViewResponse.model_validate(v) for v in views]

@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_view(id: Annotated[str, Path()], session: SessionDep):
    db_view = session.get(SavedView, id)
    if not db_view:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="View not found"
        )
    session.delete(db_view)
    session.commit()

