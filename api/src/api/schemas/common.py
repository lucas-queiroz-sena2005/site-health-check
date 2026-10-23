from typing import Generic, TypeVar
from pydantic import BaseModel, Field

T = TypeVar("T")

class Page(BaseModel, Generic[T]):
    items: list[T] = Field(default_factory=list, description="Paginated items")
    total: int = Field(ge=0, description="Total matching items count")
    limit: int = Field(ge=1, description="Page size limit")
    offset: int = Field(ge=0, description="Page offset")
