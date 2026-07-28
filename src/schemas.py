from pydantic import BaseModel, EmailStr, Field
from typing import List, Dict, Any, Optional
from datetime import date, datetime

class OwnerBase(BaseModel):
    name: str
    email: EmailStr
    business_name: str
    slug: str = Field(..., regex="^[a-z0-9-]+$") # Slug must be lowercase alphanumeric with hyphens
    phone: Optional[str] = None

class OwnerCreate(OwnerBase):
    password: str

class OwnerProfileUpdate(BaseModel):
    name: str
    business_name: str
    phone: Optional[str] = None
    # services_json and availability_json will be handled as raw strings in main.py for flexibility
    # but could also be validated here with custom validators if needed.

class Owner(OwnerBase):
    id: int
    services_json: Optional[str] = None
    availability_json: Optional[str] = None

    class Config:
        from_attributes = True

class BookingBase(BaseModel):
    customer_name: str
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    service_name: str
    booking_date: date
    booking_time: str
    status: str = "pending"

class BookingCreate(BookingBase):
    pass

class Booking(BookingBase):
    id: int
    owner_id: int
    created_at: datetime

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    id: Optional[int] = None

# For service and availability configuration (internal representation)
class Service(BaseModel):
    id: int
    name: str
    duration: int # in minutes
    price: float

class AvailabilityDay(BaseModel):
    start_time: str # e.g., "09:00"
    end_time: str   # e.g., "17:00"

class Availability(BaseModel):
    monday: List[AvailabilityDay] = []
    tuesday: List[AvailabilityDay] = []
    wednesday: List[AvailabilityDay] = []
    thursday: List[AvailabilityDay] = []
    friday: List[AvailabilityDay] = []
    saturday: List[AvailabilityDay] = []
    sunday: List[AvailabilityDay] = []