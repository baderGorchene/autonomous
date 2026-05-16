from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from typing import Optional

class BookingBase(BaseModel):
    customer_name: str
    customer_email: EmailStr
    customer_phone: str
    service: str
    datetime: datetime

class BookingCreate(BookingBase):
    pass

class Booking(BookingBase):
    id: int
    owner_id: int
    status: str
    created_at: datetime

    class Config:
        from_attributes = True

class OwnerBase(BaseModel):
    name: str
    email: EmailStr
    business_name: str
    slug: str

class OwnerCreate(OwnerBase):
    pass

class Owner(OwnerBase):
    id: int
    services_json: Optional[dict] = None
    availability_json: Optional[dict] = None

    class Config:
        from_attributes = True