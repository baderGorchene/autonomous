from pydantic import BaseModel, EmailStr, Field, validator
from typing import List, Dict, Any, Optional
import datetime

class Service(BaseModel):
    name: str
    duration: int # minutes
    price: float
    description: Optional[str] = None

class AvailabilitySlot(BaseModel):
    day_of_week: str # "Monday", "Tuesday", etc.
    start_time: str # "HH:MM"
    end_time: str # "HH:MM"

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
    availability: Dict[str, List[AvailabilitySlot]] = Field(default_factory=dict) # e.g., {"Monday": [{"start_time": "09:00", "end_time": "17:00"}]}

class Owner(OwnerBase):
    id: int
    services_json: str
    availability_json: str

    class Config:
        from_attributes = True

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
    booking_time: str # "HH:MM"

class BookingCreate(BookingBase):
    pass

class Booking(BookingBase):
    id: int
    owner_id: int
    status: str

    class Config:
        from_attributes = True

class OwnerBookings(BaseModel):
    owner: Owner
    bookings: List[Booking]

class Message(BaseModel):
    message: str
