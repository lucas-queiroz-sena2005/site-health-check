from contextlib import asynccontextmanager
import asyncio
from fastapi import FastAPI
from sqlmodel import SQLModel

from site_health_check.api.database import engine
from site_health_check.api.routers import jobs

@asynccontextmanager
async def lifespan(app: FastAPI):
    await asyncio.to_thread(SQLModel.metadata.create_all, engine)
    yield

app = FastAPI(title="Site Health Check API", lifespan=lifespan)

app.include_router(jobs.router)
