from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class UserCreate(BaseModel):
    email: str
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    created_at: datetime


class MerchantCreate(BaseModel):
    name: str
    owner_id: int


class MerchantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    owner_id: int
    created_at: datetime


class OrderCreate(BaseModel):
    merchant_id: int
    user_id: int
    amount: Decimal
    status: str = "pending"


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    merchant_id: int
    user_id: int
    amount: Decimal
    status: str
    created_at: datetime
