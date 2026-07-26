from pydantic import BaseModel, EmailStr, Field
from typing import List, Dict, Any, Optional
import datetime

class Service(BaseModel):
    name: str
    duration: int # minutes
    price: float
    description: Optional[str] = None

class Availability(BaseModel):
    day_of_week: int # 0-6 for Monday-Sunday
    start_time: str # HH:MM
    end_time: str # HH:MM

class OwnerBase(BaseModel):
    name: str
    email: EmailStr
    business_name: str
    slug: str = Field(..., regex="^[a-z0-9-]+$") # URL-friendly slug

class OwnerCreate(OwnerBase):
    password: str

class OwnerProfileUpdate(BaseModel):
    name: str
    business_name: str
    phone: Optional[str] = None
    services: List[Service]
    availability: List[Availability]

class OwnerInDB(OwnerBase):
    id: int
    phone: Optional[str] = None
    services_json: str
    availability_json: str

    class Config:
        from_attributes = True

class BookingBase(BaseModel):
    customer_name: str
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    service_name: str
    booking_date: datetime.date
    booking_time: str # HH:MM

class BookingCreate(BookingBase):
    pass

class BookingInDB(BookingBase):
    id: int
    owner_id: int
    status: str
    created_at: datetime.datetime

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None
