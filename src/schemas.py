from pydantic import BaseModel, EmailStr, Field
from typing import List, Optional, Dict
import datetime

# Service Schema (for services_json)
class Service(BaseModel):
    name: str
    description: Optional[str] = None
    duration_minutes: int
    price: float

# Availability Schema (for availability_json)
class TimeSlot(BaseModel):
    start_time: str # e.g., "09:00"
    end_time: str   # e.g., "17:00"

class DayAvailability(BaseModel):
    is_available: bool = True
    slots: List[TimeSlot] = []

class Availability(BaseModel):
    # Keys are day names, e.g., "monday", "tuesday"
    # Values are DayAvailability objects
    __root__: Dict[str, DayAvailability]

# Owner Schemas
class OwnerBase(BaseModel):
    name: str
    email: EmailStr
    business_name: str
    slug: str
    phone: Optional[str] = None

class OwnerCreate(OwnerBase):
    password: str

class Owner(OwnerBase):
    id: int
    services_json: str # Raw JSON string
    availability_json: str # Raw JSON string

    class Config:
        from_attributes = True

class OwnerProfileUpdate(BaseModel):
    name: str
    business_name: str
    phone: Optional[str] = None
    services: Optional[List[Service]] = None
    availability: Optional[Dict[str, DayAvailability]] = None

# Booking Schemas
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
    created_at: datetime.datetime

    class Config:
        from_attributes = True

# Security Schemas
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None
