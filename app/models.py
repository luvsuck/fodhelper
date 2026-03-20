from pydantic import BaseModel
from typing import Optional

class GenerateItem(BaseModel):
    productNo: str
    spec: Optional[str]
    supplierId: Optional[str]
    supplierName: Optional[str]
    length: float
