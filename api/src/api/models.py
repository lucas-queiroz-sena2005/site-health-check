from pydantic import BaseModel, ConfigDict, Field as PydanticField
from sqlmodel import Field, SQLModel, Column, JSON

class Job(SQLModel, table=True):
    __tablename__: str = "jobs"  # type: ignore

    id: int | None = Field(default=None, primary_key=True)
    targets: list[str] = Field(sa_column=Column(JSON))
    ports: list[int] = Field(sa_column=Column(JSON))
    labels: dict[str, str] = Field(default_factory=dict, sa_column=Column(JSON))

class JobCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    targets: list[str]
    ports: list[int]
    labels: dict[str, str] = PydanticField(default_factory=dict)

class JobResponse(BaseModel):
    id: int
