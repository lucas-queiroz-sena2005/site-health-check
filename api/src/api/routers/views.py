from typing import Annotated

from fastapi import APIRouter, Depends, Path, HTTPException, status
from sqlmodel import Session
from pydantic import BaseModel, ConfigDict

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

@router.post("", status_code=status.HTTP_201_CREATED)
def create_view(view_in: SavedViewCreate, session: SessionDep) -> SavedViewResponse:
    db_view = SavedView(
        name=view_in.name,
        search=view_in.search,
        statuses=view_in.statuses,
        table_sort_by=view_in.table_sort_by,
        table_sort_dir=view_in.table_sort_dir
    )
    session.add(db_view)
    session.commit()
    session.refresh(db_view)
    
    return SavedViewResponse(
        id=db_view.id,
        name=db_view.name,
        search=db_view.search,
        statuses=db_view.statuses,
        table_sort_by=db_view.table_sort_by,
        table_sort_dir=db_view.table_sort_dir
    )

@router.get("/{id}")
def get_view(id: Annotated[str, Path()], session: SessionDep) -> SavedViewResponse:
    db_view = session.get(SavedView, id)
    if not db_view:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="View not found"
        )
    
    return SavedViewResponse(
        id=db_view.id,
        name=db_view.name,
        search=db_view.search,
        statuses=db_view.statuses,
        table_sort_by=db_view.table_sort_by,
        table_sort_dir=db_view.table_sort_dir
    )

