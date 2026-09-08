from contextlib import asynccontextmanager
import asyncio
from fastapi import FastAPI, APIRouter
from sqlmodel import SQLModel

from api.database import engine
from api.routers import runs, results, views, scans, schemas

@asynccontextmanager
async def lifespan(app: FastAPI):
    await asyncio.to_thread(SQLModel.metadata.create_all, engine)
    app.state.log_subscribers = {} # type: dict[str, asyncio.Queue]
    yield

app = FastAPI(title="Site Health Check API", lifespan=lifespan)
api_router = APIRouter(prefix="/api", tags=["api"])

api_router.include_router(runs.router)
api_router.include_router(scans.router)
api_router.include_router(schemas.router)
api_router.include_router(results.router)
api_router.include_router(views.router)

app.include_router(api_router)
