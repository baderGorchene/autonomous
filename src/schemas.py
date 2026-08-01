from pydantic import BaseModel, EmailStr, Field
from typing import List, Optional, Dict
from datetime import datetime, date, time

class Service(BaseModel):
    name: str
    duration: int # minutes
    price: float
    description: Optional[str] = None

class DayAvailability(BaseModel):
    is_available: bool = True
    start_time: Optional[str] = None # e.g., "09:00"
    end_time: Optional[str] = None   # e.g., "17:00"

class Availability(BaseModel):
    monday: DayAvailability = Field(default_factory=DayAvailability)
    tuesday: DayAvailability = Field(default_factory=DayAvailability)
    wednesday: DayAvailability = Field(default_factory=DayAvailability)
    thursday: DayAvailability = Field(default_factory=DayAvailability)
    friday: DayAvailability = Field(default_factory=DayAvailability)
    saturday: DayAvailability = Field(default_factory=DayAvailability)
    sunday: DayAvailability = Field(default_factory=DayAvailability)

class OwnerBase(BaseModel):
    email: EmailStr
    name: str
    business_name: str
    slug: Optional[str] = None
    phone: Optional[str] = None

class OwnerCreate(OwnerBase):
    password: str

class Owner(OwnerBase):
    id: int
    is_active: bool
    services_json: str # JSON string
    availability_json: str # JSON string

    class Config:
        orm_mode = True

class OwnerProfileUpdate(BaseModel):
    name: str
    business_name: str
    phone: Optional[str] = None
    services_json: str = "[]"
    availability_json: str = "{}"

class BookingBase(BaseModel):
    customer_name: str
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    service_name: str
    booking_date: date
    booking_time: time
    status: str = "pending"

class BookingCreate(BookingBase):
    pass

class Booking(BookingBase):
    id: int
    owner_id: int
    created_at: datetime

    class Config:
        orm_mode = True

class Token(BaseModel):
    access_token: str
    token_type: str
    owner: Optional[Owner] = None # Include owner info on signup/login

class TokenData(BaseModel):
    email: Optional[str] = None
