from pydantic import BaseModel, EmailStr, Field
from typing import List, Optional
from datetime import date, time

class ServiceBase(BaseModel):
    name: str
    duration: int # duration in minutes

class ServiceCreate(ServiceBase):
    pass

class Service(ServiceBase):
    id: int

    class Config:
        orm_mode = True

class AvailabilityTimeRange(BaseModel):
    start: str # e.g., "09:00"
    end: str   # e.g., "17:00"

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
    services_json: str = Field(..., description="JSON string representing a list of services")
    availability_json: str = Field(..., description="JSON string representing daily availability")

class Owner(OwnerBase):
    id: int
    services_json: str # JSON string
    availability_json: str # JSON string

    class Config:
        orm_mode = True

class BookingBase(BaseModel):
    customer_name: str
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    service_name: str
    booking_date: date
    booking_time: time
    notes: Optional[str] = None

class BookingCreate(BookingBase):
    pass

class Booking(BookingBase):
    id: int
    owner_id: int

    class Config:
        orm_mode = True

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None
