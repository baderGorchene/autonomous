from pydantic import BaseModel, EmailStr, Field
from typing import List, Optional, Dict, Any
from datetime import datetime

class Service(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    duration_minutes: int = Field(..., gt=0)
    price: float = Field(..., ge=0)

class AvailabilitySlot(BaseModel):
    start_time: str
    end_time: str

class DayAvailability(BaseModel):
    is_available: bool
    slots: List[AvailabilitySlot] = []

class OwnerBase(BaseModel):
    name: str
    email: EmailStr
    business_name: str
    slug: str

class OwnerCreate(OwnerBase):
    password: str
    phone: Optional[str] = None

class OwnerUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    business_name: Optional[str] = None
    phone: Optional[str] = None
    services: Optional[List[Service]] = None
    availability: Optional[Dict[str, DayAvailability]] = None

class OwnerProfileUpdate(BaseModel):
    name: str
    business_name: str
    phone: Optional[str] = None
    services: List[Service]
    availability: Dict[str, DayAvailability]

class OwnerInDB(OwnerBase):
    id: int
    is_active: bool
    services_json: str
    availability_json: str
    phone: Optional[str] = None

    class Config:
        from_attributes = True

class Owner(OwnerInDB):
    pass

class BookingBase(BaseModel):
    customer_name: str
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    service_name: str
    booking_time: datetime

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
    email: Optional[str] = None

class LoginForm(BaseModel):
    email: EmailStr
    password: str

class SignupForm(BaseModel):
    name: str
    email: EmailStr
    password: str
    business_name: str
    slug: str
    phone: Optional[str] = None

class BookingForm(BaseModel):
    customer_name: str
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    service_name: str
    booking_date: str
    booking_time: str

class ServiceUpdateForm(BaseModel):
    services: List[Service]

class AvailabilityUpdateForm(BaseModel):
    availability: Dict[str, DayAvailability]
