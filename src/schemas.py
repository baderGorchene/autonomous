from pydantic import BaseModel, EmailStr, Field
from typing import List, Dict, Any, Optional
import datetime

class OwnerBase(BaseModel):
    name: str
    email: EmailStr
    business_name: str
    slug: str = Field(..., pattern=r"^[a-z0-9-]+$") # Slug must be lowercase alphanumeric with hyphens
    phone: Optional[str] = None

class OwnerCreate(OwnerBase):
    password: str

class Owner(OwnerBase):
    id: int
    services_json: str
    availability_json: str

    class Config:
        from_attributes = True

class OwnerProfileUpdate(BaseModel):
    name: str
    business_name: str
    phone: Optional[str] = None

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None

class Service(BaseModel):
    name: str
    duration: int # minutes
    price: float
    description: Optional[str] = None

class AvailabilitySlot(BaseModel):
    day: str # e.g., "Monday"
    start_time: str # e.g., "09:00"
    end_time: str # e.g., "17:00"

class BookingCreate(BaseModel):
    customer_name: str
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    service_name: str
    booking_date: datetime.date
    booking_time: str # e.g., "09:00 AM"

class Booking(BookingCreate):
    id: int
    owner_id: int
    status: str
    created_at: datetime.datetime

    class Config:
        from_attributes = True