from pydantic import BaseModel, EmailStr
from typing import List, Dict, Any, Optional
from datetime import datetime

class Service(BaseModel):
    name: str
    description: str
    price: float
    duration: int # in minutes

class OwnerBase(BaseModel):
    email: EmailStr
    name: str
    business_name: str
    slug: str
    phone: Optional[str] = None

class OwnerCreate(OwnerBase):
    password: str

class OwnerInDB(OwnerBase):
    id: int
    hashed_password: str
    services_json: str
    availability_json: str

    class Config:
        orm_mode = True

class OwnerProfileUpdate(BaseModel):
    name: str
    business_name: str
    phone: Optional[str] = None

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    owner_id: Optional[int] = None

class BookingBase(BaseModel):
    customer_name: str
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    service_name: str
    booking_date: datetime
    booking_time: str # e.g., "10:00 AM"

class BookingCreate(BookingBase):
    pass

class Booking(BookingBase):
    id: int
    owner_id: int
    status: str

    class Config:
        orm_mode = True

class BookingDisplay(BaseModel):
    customer_name: str
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    service_name: str
    booking_date: str # Formatted date string
    booking_time: str
    status: str

    class Config:
        orm_mode = True

class Message(BaseModel):
    message: str
