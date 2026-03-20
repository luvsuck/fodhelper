from fastapi import APIRouter
from app.services.product_service import get_spec, get_supplier

router = APIRouter(prefix="/api")

@router.get("/spec/{productNo}")
def spec(productNo: str):
    return get_spec(productNo)

@router.get("/supplier/{productNo}")
def supplier(productNo: str):
    return get_supplier(productNo)
