from fastapi import APIRouter

router = APIRouter(prefix="/api/metrics", tags=["metrics"])


@router.get("")
def get_metrics() -> dict:
    return {}
