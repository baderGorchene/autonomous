from pydantic import BaseModel, EmailStr, Field
from datetime import date, time
from typing import List, Optional, Dict, Any

class Service(BaseModel):
    name: str
    duration: int # in minutes
    price: float
    description: Optional[str] = None

class OwnerBase(BaseModel):
    name: str
    email: EmailStr
    business_name: str
    phone: Optional[str] = None

class OwnerCreate(OwnerBase):
    password: str
    slug: str

class OwnerLogin(BaseModel):
    email: EmailStr
    password: str

class OwnerProfileUpdate(BaseModel):
    name: Optional[str] = None
    business_name: Optional[str] = None
    phone: Optional[str] = None
    services_json: Optional[str] = None # JSON string of List[Service]
    availability_json: Optional[str] = None # JSON string of Dict[str, List[str]]

class Owner(OwnerBase):
    id: int
    slug: str
    services_json: str
    availability_json: str
    
    class Config:
        from_attributes = True

class BookingBase(BaseModel):
    customer_name: str
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    booking_date: date
    booking_time: time
    service_name: str # Service name is required for booking

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
