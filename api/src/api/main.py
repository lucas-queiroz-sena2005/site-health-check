import asyncio
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import SQLModel

from api.database import engine
from api.routers import results, runs, scans, schemas, views
from api.services.scheduler import scheduler_loop


@asynccontextmanager
async def lifespan(app: FastAPI):
    await asyncio.to_thread(SQLModel.metadata.create_all, engine)
    app.state.log_subscribers = {}
    app.state.run_logs = {}
    scheduler_task = asyncio.create_task(scheduler_loop(app.state))
    try:
        yield
    finally:
        scheduler_task.cancel()
        try:
            await scheduler_task
        except asyncio.CancelledError:
            pass

import anyio
from starlette.types import ASGIApp, Receive, Scope, Send

class SuppressDisconnectMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app
        
    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        try:
            await self.app(scope, receive, send)
        except ExceptionGroup as eg:
            if any(isinstance(exc, anyio.BrokenResourceError) for exc in eg.exceptions):
                return
            raise
        except anyio.BrokenResourceError:
            return

app = FastAPI(title="Site Health Check API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SuppressDisconnectMiddleware)
api_router = APIRouter(prefix="/api", tags=["api"])

api_router.include_router(runs.router)
api_router.include_router(scans.router)
api_router.include_router(schemas.router)
api_router.include_router(results.router)
api_router.include_router(views.router)

app.include_router(api_router)
