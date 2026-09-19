from fastapi import APIRouter

router = APIRouter(prefix="/api/appointments", tags=["appointments"])


@router.get("")
def list_appointments() -> list[dict]:
    return []
