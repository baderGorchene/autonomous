from pydantic import BaseModel, EmailStr
from typing import List, Dict, Any, Optional
from datetime import date, time

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    owner_id: Optional[int] = None

class OwnerBase(BaseModel):
    email: EmailStr
    name: str
    business_name: str
    slug: str
    phone: Optional[str] = None

class OwnerCreate(OwnerBase):
    password: str
    services_json: str = "[]"
    availability_json: str = "{}"

class OwnerProfileUpdate(BaseModel):
    name: str
    business_name: str
    phone: Optional[str] = None
    # services_json: str # Handled directly in main.py for now
    # availability_json: str # Handled directly in main.py for now

class OwnerInDB(OwnerBase):
    id: int
    hashed_password: str
    services_json: str
    availability_json: str

    class Config:
        orm_mode = True

class BookingBase(BaseModel):
    customer_name: str
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    service_name: str
    booking_date: date
    booking_time: time

class BookingCreate(BookingBase):
    status: str = "pending"

class Booking(BookingBase):
    id: int
    owner_id: int
    created_at: datetime
    status: str

    class Config:
        orm_mode = True
