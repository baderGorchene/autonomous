from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from typing import Optional

class BookingCreate(BaseModel):
    customer_name: str = Field(..., min_length=2, max_length=100)
    customer_email: EmailStr
    customer_phone: str = Field(..., min_length=7, max_length=20)
    service: str = Field(..., min_length=1)
    datetime: datetime

class BookingResponse(BookingCreate):
    id: int
    owner_id: int
    status: str
    created_at: datetime

    class Config:
        from_attributes = True

class OwnerCreate(BaseModel):
    name: str = Field(..., min_length=2)
    email: EmailStr
    business_name: str = Field(..., min_length=2)
    slug: str = Field(..., min_length=3, pattern='^[a-z0-9-]+$')

class OwnerResponse(OwnerCreate):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True