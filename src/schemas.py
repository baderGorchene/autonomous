from pydantic import BaseModel, EmailStr, Field
from typing import List, Dict, Optional
import datetime

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None

class OwnerBase(BaseModel):
    email: EmailStr
    name: str
    business_name: str
    slug: str = Field(..., regex="^[a-z0-9-]+$") # Slug must be lowercase alphanumeric with hyphens

class OwnerCreate(OwnerBase):
    password: str

class Service(BaseModel):
    name: str
    description: Optional[str] = None
    duration_minutes: int
    price: float

class Availability(BaseModel):
    day_of_week: int # 0=Monday, 6=Sunday
    start_time: str # "HH:MM"
    end_time: str # "HH:MM"

class OwnerProfileUpdate(BaseModel):
    name: str
    business_name: str
    phone: Optional[str] = None
    services: List[Service]
    availability: List[Availability]

class Owner(OwnerBase):
    id: int
    phone: Optional[str] = None
    is_active: bool
    services_json: str # Raw JSON string
    availability_json: str # Raw JSON string

    class Config:
        from_attributes = True

class BookingBase(BaseModel):
    customer_name: str
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    service_name: str
    booking_date: datetime.date
    booking_time: str # "HH:MM"

class BookingCreate(BookingBase):
    pass

class Booking(BookingBase):
    id: int
    owner_id: int
    status: str
    
    class Config:
        from_attributes = True
