from pydantic import BaseModel
from typing import List, Dict, Optional
from datetime import datetime

class OwnerBase(BaseModel):
    name: str
    email: str
    business_name: str
    slug: str

class OwnerCreate(OwnerBase):
    password: str

class OwnerProfileUpdate(BaseModel):
    name: str
    business_name: str
    phone: Optional[str] = None

class Owner(OwnerBase):
    id: int
    services_json: List[Dict]
    availability_json: Dict
    phone: Optional[str] = None
    created_at: datetime

    class Config:
        orm_mode = True

class BookingBase(BaseModel):
    customer_name: str
    customer_email: str
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
        orm_mode = True