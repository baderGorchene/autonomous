from pydantic import BaseModel, EmailStr, Field
from typing import List, Dict, Optional
from datetime import datetime

class Service(BaseModel):
    name: str
    duration_minutes: int
    price: float

class OwnerCreate(BaseModel):
    name: str
    email: EmailStr
    business_name: str
    slug: str
    services: List[Service]

class BookingCreate(BaseModel):
    customer_name: str
    customer_email: EmailStr
    customer_phone: str
    service_name: str
    datetime: datetime

class BookingResponse(BookingCreate):
    id: int
    owner_id: int
    status: str
    created_at: datetime

    class Config:
        from_attributes = True