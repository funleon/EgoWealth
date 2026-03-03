from pydantic import BaseModel, Field
from typing import Literal

class TransactionBase(BaseModel):
    ticker: str = Field(..., max_length=20)
    action: Literal["BUY", "SELL"]
    price: float = Field(..., gt=0)
    quantity: float = Field(..., gt=0)

class TransactionCreate(TransactionBase):
    pass

class TransactionDelete(BaseModel):
    tx_id: str

class ImpersonateRequest(BaseModel):
    target_user_id: str
