from pydantic import BaseModel, EmailStr
from typing import List, Dict, Optional
import datetime

class OwnerBase(BaseModel):
    name: str
    email: EmailStr
    business_name: str
    phone: Optional[str] = None

class OwnerCreate(OwnerBase):
    password: str
    slug: Optional[str] = None # Slug can be optional, generated if not provided

class Owner(OwnerBase):
    id: int
    slug: str
    services_json: str
    availability_json: str

    class Config:
        orm_mode = True

class OwnerProfileUpdate(BaseModel):
    name: str
    business_name: str
    phone: Optional[str] = None
    services: List[Dict] = []
    availability: Dict = {}

class Token(BaseModel):
    access_token: str
    token_type: str
    owner: Owner # Added owner to the token response

class TokenData(BaseModel):
    email: Optional[str] = None

class Service(BaseModel):
    name: str
    duration: int # in minutes
    price: float

class AvailabilitySlot(BaseModel):
    day_of_week: int # 0-6 for Monday-Sunday
    start_time: str # HH:MM
    end_time: str # HH:MM

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

    class Config:
        orm_mode = True
