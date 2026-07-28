from pydantic import BaseModel, EmailStr
from typing import List, Dict, Any, Optional
from datetime import date, time

class ServiceBase(BaseModel):
    name: str
    duration: int
    price: Optional[float] = None

class AvailabilitySlot(BaseModel):
    start_time: str
    end_time: str

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
    services_json: str
    availability_json: str

    class Config:
        from_attributes = True

class BookingBase(BaseModel):
    customer_name: str
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    service_name: str
    booking_date: date
    booking_time: time

class BookingCreate(BookingBase):
    pass

class Booking(BookingBase):
    id: int
    owner_id: int

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None