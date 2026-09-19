from fastapi import FastAPI

from fastapi.staticfiles import StaticFiles

from app.api.routes import (
    appointments,
    benchmark,
    disruptions,
    execution,
    health,
    memory,
    metrics,
    preferences,
    recovery,
    voice,
)
from app.db import models  # noqa: F401 - registers tables on Base before create_all
from app.db.session import Base, engine

Base.metadata.create_all(bind=engine)

app = FastAPI(title="SlotSaver API")

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

app.mount("/playground", StaticFiles(directory="app/playground", html=True), name="playground")
