from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from typing import List, Dict, Optional

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None

class OwnerBase(BaseModel):
    name: str
    email: EmailStr
    business_name: str
    slug: str = Field(..., regex="^[a-z0-9-]+$", min_length=3, max_length=50)
    phone: Optional[str] = None

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

    class Config:
        from_attributes = True

class BookingBase(BaseModel):
    customer_name: str
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    service_name: str
    booking_date: datetime
    booking_time: str
    message: Optional[str] = None

class BookingCreate(BookingBase):
    pass

class Booking(BookingBase):
    id: int
    owner_id: int
    created_at: datetime

    class Config:
        from_attributes = True

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class Service(BaseModel):
    name: str
    description: Optional[str] = None
    price: float
    duration_minutes: int

class AvailabilitySlot(BaseModel):
    day_of_week: int
    start_time: str
    end_time: str
