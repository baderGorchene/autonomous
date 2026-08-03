from pydantic import BaseModel, EmailStr, Field
from datetime import date, time
from typing import List, Dict, Any, Optional

class ServiceSchema(BaseModel):
    name: str
    duration: int # in minutes
    price: float
    description: Optional[str] = None

class AvailabilitySchema(BaseModel):
    day_of_week: int # 0=Monday, 6=Sunday
    start_time: time
    end_time: time

class OwnerBase(BaseModel):
    name: str
    email: EmailStr
    business_name: str
    slug: str = Field(..., regex="^[a-z0-9-]+$") # URL friendly slug
    phone: Optional[str] = None

class OwnerCreate(OwnerBase):
    password: str

class OwnerProfileUpdate(BaseModel):
    name: str
    business_name: str
    phone: Optional[str] = None
    services: Optional[List[ServiceSchema]] = None
    availability: Optional[List[AvailabilitySchema]] = None

class Owner(OwnerBase):
    id: int
    services_json: str
    availability_json: str

    class Config:
        orm_mode = True

class BookingBase(BaseModel):
    customer_name: str
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    booking_date: date
    booking_time: time
    service_name: str

class BookingCreate(BookingBase):
    pass

class Booking(BookingBase):
    id: int
    owner_id: int
    status: str

    class Config:
        orm_mode = True

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None
