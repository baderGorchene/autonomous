from pydantic import BaseModel, EmailStr
from datetime import date, time, datetime
from typing import List, Optional
from .models import RecurrenceType

class OwnerBase(BaseModel):
    email: EmailStr
    name: str
    phone: Optional[str] = None

class OwnerCreate(OwnerBase):
    password: str

class Owner(OwnerBase):
    id: int
    is_premium: bool = False
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None

    class Config:
        orm_mode = True

class ServiceBase(BaseModel):
    name: str
    description: Optional[str] = None
    duration_minutes: int
    price: float

class ServiceCreate(ServiceBase):
    pass

class Service(ServiceBase):
    id: int
    owner_id: int
    bookings: List["Booking"] = []
    availabilities: List["Availability"] = []

    class Config:
        orm_mode = True

class BookingBase(BaseModel):
    service_id: int
    date: date
    time: time
    customer_name: str
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    is_recurring: bool = False
    recurrence_type: Optional[RecurrenceType] = None
    recurrence_value: Optional[str] = None
    recurrence_end_date: Optional[date] = None

class BookingCreate(BookingBase):
    pass

class Booking(BookingBase):
    id: int
    owner_id: int
    created_at: datetime

    class Config:
        orm_mode = True

class AvailabilityBase(BaseModel):
    start_time: time
    end_time: time
    date: Optional[date] = None
    service_id: Optional[int] = None
    recurrence_type: Optional[RecurrenceType] = None
    recurrence_value: Optional[str] = None
    recurrence_start_date: Optional[date] = None
    recurrence_end_date: Optional[date] = None

class AvailabilityCreate(AvailabilityBase):
    pass

class Availability(AvailabilityBase):
    id: int
    owner_id: int

    class Config:
        orm_mode = True

class Token(BaseModel):
    access_token: str
    token_type: str

# Update forward refs
Service.update_forward_refs()
Booking.update_forward_refs()
