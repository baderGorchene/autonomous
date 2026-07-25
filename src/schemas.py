from pydantic import BaseModel, EmailStr, Field
from typing import List, Dict, Any, Optional
from datetime import datetime

class Service(BaseModel):
    name: str
    description: Optional[str] = None
    duration_minutes: int
    price: float

class AvailabilitySlot(BaseModel):
    day_of_week: int # 0=Monday, 6=Sunday
    start_time: str # HH:MM
    end_time: str # HH:MM

class OwnerBase(BaseModel):
    email: EmailStr

class OwnerCreate(OwnerBase):
    name: str
    password: str
    business_name: str
    slug: str

class OwnerLogin(OwnerBase):
    password: str

class OwnerProfileUpdate(BaseModel):
    name: str
    business_name: str
    phone: Optional[str] = None

class Owner(OwnerBase):
    id: int
    name: str
    business_name: str
    slug: str
    phone: Optional[str] = None
    services_json: str # JSON string for services
    availability_json: str # JSON string for availability

    class Config:
        from_attributes = True

class BookingBase(BaseModel):
    customer_name: str
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    service_name: str
    booking_time: datetime

class BookingCreate(BookingBase):
    pass

class Booking(BookingBase):
    id: int
    owner_id: int
    status: str
    created_at: datetime

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None
