from pydantic import BaseModel, EmailStr, Field
from typing import List, Dict, Any, Optional
from datetime import datetime

class ServiceBase(BaseModel):
    name: str
    description: Optional[str] = None
    duration_minutes: int
    price: float

class ServiceCreate(ServiceBase):
    pass

class Service(ServiceBase):
    id: int

    class Config:
        from_attributes = True

class Availability(BaseModel):
    day_of_week: int # 0=Monday, 6=Sunday
    start_time: str # e.g., "09:00"
    end_time: str # e.g., "17:00"

class OwnerBase(BaseModel):
    email: EmailStr
    name: str
    business_name: str
    slug: str
    phone: Optional[str] = None

class OwnerCreate(OwnerBase):
    password: str
    services: Optional[List[ServiceCreate]] = []
    availability: Optional[Dict[str, List[Availability]]] = {} # e.g., {"MONDAY": [...]}

class OwnerLogin(BaseModel):
    email: EmailStr
    password: str

class OwnerProfileUpdate(BaseModel):
    name: str
    business_name: str
    phone: Optional[str] = None

class Owner(OwnerBase):
    id: int
    is_active: bool = True
    services_json: str
    availability_json: str
    bookings: List["Booking"] = []

    class Config:
        from_attributes = True

class BookingBase(BaseModel):
    customer_name: str
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    service_name: str
    booking_date: datetime # This should be a date, but datetime is fine for now
    booking_time: str # e.g., "10:00"

class BookingCreate(BookingBase):
    pass

class Booking(BookingBase):
    id: int
    owner_id: int
    created_at: datetime

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    owner_id: Optional[int] = None

# Add a forward reference for Booking in Owner
Owner.model_rebuild()