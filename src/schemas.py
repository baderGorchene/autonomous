from pydantic import BaseModel, EmailStr, Field
from typing import List, Dict, Any, Optional
import datetime

class OwnerBase(BaseModel):
    name: str
    email: EmailStr
    business_name: str
    slug: str = Field(..., regex="^[a-z0-9-]+$", min_length=3, max_length=50) # Slug for public booking page
    phone: Optional[str] = None

class OwnerCreate(OwnerBase):
    password: str

class OwnerLogin(BaseModel):
    email: EmailStr
    password: str

class OwnerProfileUpdate(BaseModel):
    name: str
    business_name: str
    phone: Optional[str] = None
    services: List[Dict[str, Any]] = []
    availability: Dict[str, Any] = {}

class Owner(OwnerBase):
    id: int
    services_json: str
    availability_json: str

    class Config:
        from_attributes = True

class Service(BaseModel):
    name: str
    duration: int # duration in minutes
    price: float
    description: Optional[str] = None

class AvailabilitySlot(BaseModel):
    day_of_week: str # e.g., "Monday"
    start_time: str # e.g., "09:00"
    end_time: str # e.g., "17:00"

class BookingBase(BaseModel):
    customer_name: str
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    service_name: str
    booking_date: datetime.date
    booking_time: str # e.g., "10:00 AM"

class BookingCreate(BookingBase):
    pass

class Booking(BookingBase):
    id: int
    owner_id: int
    status: str

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None