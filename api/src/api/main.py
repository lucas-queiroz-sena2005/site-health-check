from contextlib import asynccontextmanager
import asyncio
from fastapi import FastAPI
from sqlmodel import SQLModel

from api.database import engine
from api.routers import jobs, results, views, schedules, schemas

@asynccontextmanager
async def lifespan(app: FastAPI):
    await asyncio.to_thread(SQLModel.metadata.create_all, engine)
    yield

app = FastAPI(title="Site Health Check API", lifespan=lifespan)

app.include_router(jobs.router)
app.include_router(schedules.router)
app.include_router(schemas.router)
app.include_router(results.router)
app.include_router(views.router)

