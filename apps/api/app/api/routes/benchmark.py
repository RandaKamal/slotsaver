from fastapi import APIRouter

from app.agents.benchmark import run_benchmark

router = APIRouter(prefix="/api/benchmark", tags=["benchmark"])


@router.get("/run")
def run(include_slow: bool = False) -> dict:
    return run_benchmark(include_slow=include_slow)
