from fastapi import APIRouter

router = APIRouter(prefix="/api/disruptions", tags=["disruptions"])


@router.post("/analyze")
def analyze_disruption(payload: dict) -> dict:
    return {}
