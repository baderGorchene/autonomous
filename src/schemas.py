from pydantic import BaseModel, EmailStr, Field
from typing import List, Optional
import datetime

class Service(BaseModel):
    name: str
    duration_minutes: int
    price: float

class Availability(BaseModel):
    day_of_week: int # Monday is 0, Sunday is 6
    start_time: str # HH:MM
    end_time: str # HH:MM

class OwnerBase(BaseModel):
    name: str
    email: EmailStr
    business_name: str
    slug: str = Field(..., pattern=r"^[a-z0-9-]+$", min_length=3, max_length=50) # Slug validation
    phone: Optional[str] = None

class OwnerCreate(OwnerBase):
    password: str

class OwnerProfileUpdate(BaseModel):
    name: str
    business_name: str
    phone: Optional[str] = None
    # services: Optional[List[Service]] = None # Not directly updating via this schema for now
    # availability: Optional[List[Availability]] = None # Not directly updating via this schema for now

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
    booking_date: datetime.date
    booking_time: str

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