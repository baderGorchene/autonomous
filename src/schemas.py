from pydantic import BaseModel, EmailStr
from typing import List, Dict, Any, Optional
import datetime

# --- Token Schemas ---
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None

# --- Service Schemas (for services_json) ---
class Service(BaseModel):
    name: str
    duration: int # in minutes
    price: float
    description: Optional[str] = None

# --- Availability Schemas (for availability_json) ---
class DayAvailability(BaseModel):
    start_time: str # e.g., "09:00"
    end_time: str   # e.g., "17:00"
    slot_duration: int # in minutes, e.g., 30

class Availability(BaseModel):
    monday: Optional[List[DayAvailability]] = None
    tuesday: Optional[List[DayAvailability]] = None
    wednesday: Optional[List[DayAvailability]] = None
    thursday: Optional[List[DayAvailability]] = None
    friday: Optional[List[DayAvailability]] = None
    saturday: Optional[List[DayAvailability]] = None
    sunday: Optional[List[DayAvailability]] = None

# --- Owner Schemas ---
class OwnerBase(BaseModel):
    name: str
    email: EmailStr
    business_name: str
    slug: str

class OwnerCreate(OwnerBase):
    password: str

class OwnerProfileUpdate(BaseModel):
    name: Optional[str] = None
    business_name: Optional[str] = None
    phone: Optional[str] = None
    services: Optional[List[Service]] = None # For updating services_json
    availability: Optional[Availability] = None # For updating availability_json

class OwnerInDB(OwnerBase):
    id: int
    services_json: str
    availability_json: str
    phone: Optional[str] = None

    class Config:
        orm_mode = True

# --- Booking Schemas ---
class BookingBase(BaseModel):
    customer_name: str
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    service_name: str
    booking_time: datetime.datetime

class BookingCreate(BookingBase):
    pass

class BookingDisplay(BookingBase):
    id: int
    owner_id: int
    status: str

    class Config:
        orm_mode = True
