from pydantic import BaseModel
from typing import List, Dict, Optional
from datetime import datetime

class OwnerBase(BaseModel):
    name: str
    email: str
    business_name: str
    slug: str
    phone: Optional[str] = None

class OwnerCreate(OwnerBase):
    password: str

class Owner(OwnerBase):
    id: int
    services_json: List[Dict]
    availability_json: Dict
    created_at: datetime

    class Config:
        from_attributes = True

class OwnerProfileUpdate(BaseModel):
    name: str
    business_name: str
    phone: Optional[str] = None

class BookingBase(BaseModel):
    customer_name: str
    customer_email: str
    customer_phone: Optional[str] = None
    service: str
    datetime: datetime

class BookingCreate(BookingBase):
    pass

class Booking(BookingBase):
    id: int
    owner_id: int
    status: str = "pending"
    created_at: datetime

    class Config:
        from_attributes = True
