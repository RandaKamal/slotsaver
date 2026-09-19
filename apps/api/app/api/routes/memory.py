from fastapi import APIRouter

router = APIRouter(prefix="/api/memory", tags=["memory"])


@router.get("/{customer_id}")
def get_customer_memory(customer_id: str) -> dict:
    return {}
