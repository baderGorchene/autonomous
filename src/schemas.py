from pydantic import BaseModel, EmailStr, Field
from typing import List, Optional
import datetime

class Service(BaseModel):
    name: str
    duration: int # in minutes
    price: float

class AvailabilitySlot(BaseModel):
    day_of_week: int # 0=Monday, 6=Sunday
    start_time: str # HH:MM
    end_time: str   # HH:MM

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
    services: List[Service] = []
    availability: List[AvailabilitySlot] = []

class OwnerInDB(OwnerBase):
    id: int
    services_json: str
    availability_json: str
    created_at: datetime.datetime
    updated_at: Optional[datetime.datetime] = None

    class Config:
        from_attributes = True

class BookingBase(BaseModel):
    customer_name: str
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    service_name: str
    booking_date: str # YYYY-MM-DD
    booking_time: str # HH:MM

class BookingCreate(BookingBase):
    pass

class BookingInDB(BookingBase):
    id: int
    owner_id: int
    status: str
    created_at: datetime.datetime

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None

class LoginSchema(BaseModel):
    email: EmailStr
    password: str
