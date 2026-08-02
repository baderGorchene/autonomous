from pydantic import BaseModel, EmailStr, Field
from typing import List, Dict, Any, Optional
from datetime import datetime

class ServiceBase(BaseModel):
    name: str
    duration: int # in minutes
    price: float
    description: Optional[str] = None

class ServiceCreate(ServiceBase):
    pass

class Service(ServiceBase):
    id: int
    class Config:
        from_attributes = True

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

class OwnerLogin(BaseModel):
    email: EmailStr
    password: str

class Owner(OwnerBase):
    id: int
    is_active: bool = True
    services: List[Service] = [] # This will be handled as JSON in the model
    availability: Dict[str, Any] = {} # This will be handled as JSON in the model

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None

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
    created_at: datetime

    class Config:
        from_attributes = True
