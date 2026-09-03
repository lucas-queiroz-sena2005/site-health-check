from contextlib import asynccontextmanager
import asyncio
from fastapi import FastAPI
from sqlmodel import SQLModel

from api.database import engine
from api.routers import jobs, results, views, schedules, schemas

@asynccontextmanager
async def lifespan(app: FastAPI):
    await asyncio.to_thread(SQLModel.metadata.create_all, engine)
    app.state.log_subscribers = {} # type: dict[str, asyncio.Queue]
    yield

app = FastAPI(title="Site Health Check API", lifespan=lifespan)

app.include_router(jobs.router, prefix="/api")
app.include_router(schedules.router, prefix="/api")
app.include_router(schemas.router, prefix="/api")
app.include_router(results.router, prefix="/api")
app.include_router(views.router, prefix="/api")

