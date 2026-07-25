from pydantic import BaseModel, EmailStr, Field
from typing import List, Dict, Any, Optional
import datetime

class Service(BaseModel):
    name: str
    duration_minutes: int
    price: str

class AvailabilitySlot(BaseModel):
    day_of_week: str # e.g., "Monday"
    start_time: str # e.g., "09:00"
    end_time: str # e.g., "17:00"

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
    services: Optional[List[Service]] = None
    availability: Optional[List[AvailabilitySlot]] = None

class Owner(OwnerBase):
    id: int
    phone: Optional[str] = None
    # services and availability are loaded from JSON strings in the model
    # For Pydantic, we'll represent them as List[Service] and List[AvailabilitySlot]
    # The actual ORM model will store them as JSON strings

    class Config:
        orm_mode = True
        # We'll handle the JSON (de)serialization in the API layer or using hybrid properties

class BookingBase(BaseModel):
    customer_name: str
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    service_name: str
    booking_time: datetime.datetime

class BookingCreate(BookingBase):
    pass

class Booking(BookingBase):
    id: int
    owner_id: int
    created_at: datetime.datetime

    class Config:
        orm_mode = True

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None
