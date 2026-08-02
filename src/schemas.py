from pydantic import BaseModel, EmailStr
from typing import List, Optional, Dict, Any
from datetime import date, time, datetime

class Service(BaseModel):
    name: str
    duration_minutes: int
    price: float

class AvailabilitySlot(BaseModel):
    start: str
    end: str

class OwnerBase(BaseModel):
    name: str
    email: EmailStr
    business_name: str
    slug: str
    phone: str

class OwnerCreate(OwnerBase):
    password: str
    services: Optional[List[Service]] = None
    availability: Optional[Dict[str, List[AvailabilitySlot]]] = None

class OwnerProfileUpdate(BaseModel):
    name: str
    business_name: str
    phone: str

class Owner(OwnerBase):
    id: int
    is_active: bool = True
    services_json: str # Store JSON string
    availability_json: str # Store JSON string

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str
    owner: Owner # Include owner details for convenience

class TokenData(BaseModel):
    email: Optional[str] = None

class BookingBase(BaseModel):
    customer_name: str
    customer_email: EmailStr
    customer_phone: str
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
    updated_at: datetime

    class Config:
        from_attributes = True