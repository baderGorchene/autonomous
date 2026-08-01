from pydantic import BaseModel, EmailStr, Field
from typing import List, Dict, Any, Optional
import datetime

class Service(BaseModel):
    name: str
    duration: int # in minutes
    price: float
    description: Optional[str] = None

class AvailabilitySlot(BaseModel):
    day: str # e.g., "Monday"
    start_time: str # e.g., "09:00"
    end_time: str # e.g., "17:00"

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
    services: List[Service] = Field(default_factory=list)
    availability: Dict[str, List[AvailabilitySlot]] = Field(default_factory=dict)

class Owner(OwnerBase):
    id: int
    services_json: str
    availability_json: str
    is_active: bool = True

    class Config:
        from_attributes = True # Changed from orm_mode = True for Pydantic v2

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
    booking_date: datetime.date
    booking_time: str

class BookingCreate(BookingBase):
    pass

class Booking(BookingBase):
    id: int
    owner_id: int
    status: str
    created_at: datetime.datetime

    class Config:
        from_attributes = True
