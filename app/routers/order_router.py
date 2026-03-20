from fastapi import APIRouter
from app.services.order_service import get_order_materials

router = APIRouter(prefix="/api/order")

@router.get("/{finishedOrderId}")
def order(finishedOrderId: int):
    return get_order_materials(finishedOrderId)
