from pydantic import BaseModel, EmailStr, Field
from typing import List, Dict, Any, Optional
import datetime

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None

class OwnerBase(BaseModel):
    email: EmailStr
    name: str
    business_name: str
    slug: str

class OwnerCreate(OwnerBase):
    password: str

class OwnerProfileUpdate(BaseModel):
    name: str
    business_name: str
    phone: Optional[str] = None
    services: List[Dict[str, Any]] = Field(default_factory=list)
    availability: Dict[str, Any] = Field(default_factory=dict)

class Owner(OwnerBase):
    id: int
    is_active: bool
    services_json: str
    availability_json: str
    phone: Optional[str] = None

    class Config:
        from_attributes = True

class Service(BaseModel):
    name: str
    duration: int # in minutes
    price: Optional[float] = None
    description: Optional[str] = None

class AvailabilitySlot(BaseModel):
    day: str # e.g., "Monday"
    start_time: str # e.g., "09:00"
    end_time: str # e.g., "17:00"

class BookingBase(BaseModel):
    customer_name: str
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    service_name: str
    booking_date: datetime.date
    booking_time: str # HH:MM string
    notes: Optional[str] = None

class BookingCreate(BookingBase):
    pass

class Booking(BookingBase):
    id: int
    owner_id: int
    created_at: datetime.datetime

    class Config:
        from_attributes = True
