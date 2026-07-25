from pydantic import BaseModel, EmailStr
from typing import List, Dict, Any, Optional
from datetime import datetime

class Service(BaseModel):
    name: str
    description: Optional[str] = None
    duration_minutes: int
    price: Optional[float] = None

class AvailabilitySlot(BaseModel):
    start_time: str
    end_time: str

class OwnerBase(BaseModel):
    name: str
    email: EmailStr
    business_name: str
    slug: str

class OwnerCreate(OwnerBase):
    password: str

class OwnerProfileUpdate(BaseModel):
    name: str
    business_name: str
    phone: Optional[str] = None

class Owner(OwnerBase):
    id: int
    phone: Optional[str] = None
    services_json: List[Service] = []
    availability_json: Dict[str, List[AvailabilitySlot]] = {}

    class Config:
        from_attributes = True

class OwnerLogin(BaseModel):
    email: EmailStr
    password: str

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
    booking_time: datetime
    duration_minutes: int

class BookingCreate(BookingBase):
    pass

class Booking(BookingBase):
    id: int
    owner_id: int
    created_at: datetime

    class Config:
        from_attributes = True

class BookingDisplay(BaseModel):
    customer_name: str
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    service_name: str
    booking_time: datetime

    class Config:
        from_attributes = True

class MessageResponse(BaseModel):
    message: str
