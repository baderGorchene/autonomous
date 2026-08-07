from pydantic import BaseModel, EmailStr, Field
from datetime import date, time, datetime
from typing import List, Optional

class OwnerBase(BaseModel):
    name: str
    email: EmailStr
    business_name: str
    slug: str = Field(..., min_length=3, max_length=50, pattern="^[a-z0-9-]+$")
    phone: Optional[str] = None

class OwnerCreate(OwnerBase):
    password: str

class Owner(OwnerBase):
    id: int
    is_active: bool = True
    services_json: str # JSON string of services
    availability_json: str # JSON string of availability

    class Config:
        from_attributes = True

class OwnerProfileUpdate(BaseModel):
    name: str
    business_name: str
    phone: Optional[str] = None
    services_json: Optional[str] = None
    availability_json: Optional[str] = None


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
    created_at: datetime

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None
