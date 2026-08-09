from pydantic import BaseModel, EmailStr
from typing import List, Optional
from datetime import date, time, datetime
from .models import RecurrenceType

class OwnerBase(BaseModel):
    email: EmailStr
    full_name: str
    phone_number: Optional[str] = None

class OwnerCreate(OwnerBase):
    password: str

class Owner(OwnerBase):
    id: int
    is_active: bool
    stripe_customer_id: Optional[str] = None
    subscription_status: str

    class Config:
        orm_mode = True

class ServiceBase(BaseModel):
    name: str
    description: Optional[str] = None
    duration_minutes: int
    price: int
    currency: str

class ServiceCreate(ServiceBase):
    pass

class Service(ServiceBase):
    id: int
    owner_id: int

    class Config:
        orm_mode = True

class AvailabilityBase(BaseModel):
    service_id: Optional[int] = None
    date: Optional[date] = None
    start_time: time
    end_time: time
    
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

class BookingBase(BaseModel):
    service_id: int
    customer_name: str
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    date: date
    time: time
    recurring_booking_id: Optional[int] = None

class BookingCreate(BookingBase):
    pass

class BookingResponse(BookingBase):
    id: int
    owner_id: int
    created_at: datetime

    class Config:
        orm_mode = True

class RecurringBookingBase(BaseModel):
    service_id: int
    customer_name: str
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    start_time: time
    duration_minutes: int
    recurrence_type: RecurrenceType
    recurrence_value: Optional[str] = None
    start_date: date
    end_date: Optional[date] = None

class RecurringBookingCreate(RecurringBookingBase):
    pass

class RecurringBookingDisplay(RecurringBookingBase):
    id: int
    owner_id: int
    created_at: datetime
    
    class Config:
        orm_mode = True

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None
