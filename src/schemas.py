from pydantic import BaseModel, EmailStr, Field
from typing import List, Optional
import datetime

class Service(BaseModel):
    name: str
    duration: int # minutes
    price: float
    currency: str = "USD"
    description: Optional[str] = None

class AvailabilitySlot(BaseModel):
    day_of_week: int # 0=Monday, 6=Sunday
    start_time: str # HH:MM
    end_time: str # HH:MM

class OwnerBase(BaseModel):
    name: str
    email: EmailStr
    business_name: str
    slug: str
    phone: Optional[str] = None

class OwnerCreate(OwnerBase):
    password: str

class OwnerInDB(OwnerBase):
    id: int
    services_json: str
    availability_json: str

    class Config:
        from_attributes = True

class OwnerProfileUpdate(BaseModel):
    name: str
    business_name: str
    phone: Optional[str] = None

class BookingBase(BaseModel):
    customer_name: str
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    service_name: str
    booking_date: datetime.date
    booking_time: str

class BookingCreate(BookingBase):
    pass

class BookingInDB(BookingBase):
    id: int
    owner_id: int
    created_at: datetime.datetime

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None

class ServiceSetup(BaseModel):
    services: List[Service]
    availability: List[AvailabilitySlot]

class BookingForm(BaseModel):
    customer_name: str = Field(..., min_length=1)
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    service_name: str = Field(..., min_length=1)
    booking_date: str # YYYY-MM-DD
    booking_time: str # HH:MM
    csrf_token: str # For CSRF protection