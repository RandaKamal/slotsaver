import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import (
    appointments,
    benchmark,
    disruptions,
    execution,
    health,
    memory,
    metrics,
    outreach,
    preferences,
    recovery,
    voice,
)
from app.db import models  # noqa: F401 - registers tables on Base before create_all
from app.db.migrate import ensure_columns
from app.db.session import Base, engine
from app.services.recovery_scheduler import run_forever as run_recovery_scheduler

logger = logging.getLogger(__name__)

Base.metadata.create_all(bind=engine)
# create_all skips tables that already exist, so columns added later need this.
for _added in ensure_columns(engine):
    print(f"[db] added missing column {_added}")


@asynccontextmanager
async def lifespan(_: FastAPI):
    # The autonomous recovery scheduler (timeout advance, incentive fallback,
    # planning freshly-cancelled slots) - runs independent of any request or
    # button click. See recovery_scheduler.py.
    task = asyncio.create_task(run_recovery_scheduler())
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="SlotSaver API", lifespan=lifespan)

# The Next.js dev server (:3000) calls this API (:8000) cross-origin — the
# browser blocks that without CORS. Dev-only origins; tighten before deploy.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(appointments.router)
app.include_router(disruptions.router)
app.include_router(preferences.router)
app.include_router(benchmark.router)
app.include_router(recovery.router)
app.include_router(execution.router)
app.include_router(memory.router)
app.include_router(metrics.router)
app.include_router(voice.router)
app.include_router(outreach.router)

app.mount("/playground", StaticFiles(directory="app/playground", html=True), name="playground")
