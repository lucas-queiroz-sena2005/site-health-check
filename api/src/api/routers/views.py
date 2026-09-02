from typing import Annotated

from fastapi import APIRouter, Depends, Path, HTTPException, status
from sqlmodel import Session

from api.database import get_session
from api.models import SavedView, SavedViewCreate, SavedViewResponse

router = APIRouter(prefix="/views", tags=["views"])

SessionDep = Annotated[Session, Depends(get_session)]

@router.post("", status_code=status.HTTP_201_CREATED)
def create_view(view_in: SavedViewCreate, session: SessionDep) -> SavedViewResponse:
    db_view = SavedView(view_state=view_in.view_state)
    session.add(db_view)
    session.commit()
    session.refresh(db_view)
    
    # ID is guaranteed to be an int after flush/commit
    assert db_view.id is not None
    
    return SavedViewResponse(id=db_view.id, view_state=db_view.view_state)

@router.get("/{id}")
def get_view(id: Annotated[int, Path()], session: SessionDep) -> SavedViewResponse:
    db_view = session.get(SavedView, id)
    if not db_view:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="View not found"
        )
    
    assert db_view.id is not None
    return SavedViewResponse(id=db_view.id, view_state=db_view.view_state)
