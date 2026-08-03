from pydantic import BaseModel, EmailStr, Field
from typing import List, Dict, Any, Optional
from datetime import date, datetime

class Service(BaseModel):
    name: str
    duration_minutes: int
    price: float

class AvailabilitySlot(BaseModel):
    start_time: str # e.g., "09:00"
    end_time: str   # e.g., "17:00"

class DailyAvailability(BaseModel):
    day_of_week: int # 0=Monday, 6=Sunday
    slots: List[AvailabilitySlot]

class OwnerBase(BaseModel):
    name: str
    email: EmailStr
    business_name: str
    slug: str
    phone: Optional[str] = None

class OwnerCreate(OwnerBase):
    password: str

class OwnerProfileUpdate(BaseModel):
    name: str
    business_name: str
    phone: Optional[str] = None

class Owner(OwnerBase):
    id: int
    is_active: bool
    services_json: str
    availability_json: str

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None

class BookingBase(BaseModel):
    customer_name: str
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    service_name: str
    booking_date: date
    booking_time: str # e.g., "09:00-10:00"

class BookingCreate(BookingBase):
    pass

class Booking(BookingBase):
    id: int
    owner_id: int
    status: str
    created_at: datetime

    class Config:
        from_attributes = True

