from contextlib import asynccontextmanager
import asyncio
from fastapi import FastAPI, APIRouter
from sqlmodel import SQLModel

from api.database import engine
from api.routers import runs, results, views, scans, schemas

from api.services.scheduler import scheduler_loop

@asynccontextmanager
async def lifespan(app: FastAPI):
    await asyncio.to_thread(SQLModel.metadata.create_all, engine)
    app.state.log_subscribers = {} # type: dict[str, list[asyncio.Queue]]
    app.state.run_logs = {} # type: dict[str, list]
    scheduler_task = asyncio.create_task(scheduler_loop(app.state))
    try:
        yield
    finally:
        scheduler_task.cancel()
        try:
            await scheduler_task
        except asyncio.CancelledError:
            pass

app = FastAPI(title="Site Health Check API", lifespan=lifespan)
api_router = APIRouter(prefix="/api", tags=["api"])

api_router.include_router(runs.router)
api_router.include_router(scans.router)
api_router.include_router(schemas.router)
api_router.include_router(results.router)
api_router.include_router(views.router)

app.include_router(api_router)
