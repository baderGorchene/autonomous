from pydantic import BaseModel, EmailStr, Field
from datetime import date, time, datetime
from typing import List, Optional
import uuid

from .models import RecurrenceType

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None

class OwnerBase(BaseModel):
    email: EmailStr
    username: str
    phone_number: Optional[str] = None
    language: Optional[str] = "en"

class OwnerCreate(OwnerBase):
    password: str

class Owner(OwnerBase):
    id: int
    is_active: bool
    subscription_status: str
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None

    class Config:
        orm_mode = True

class ServiceBase(BaseModel):
    name: str
    description: Optional[str] = None
    duration_minutes: int = Field(..., gt=0)
    price: int = Field(..., ge=0)

class ServiceCreate(ServiceBase):
    pass

class Service(ServiceBase):
    id: int
    owner_id: int

    class Config:
        orm_mode = True

class CustomerBase(BaseModel):
    name: str
    email: EmailStr
    phone_number: Optional[str] = None

class CustomerCreate(CustomerBase):
    pass

class Customer(CustomerBase):
    id: int

    class Config:
        orm_mode = True

class BookingBase(BaseModel):
    service_id: int
    date: date
    time: time
    customer_name: str
    customer_email: EmailStr
    customer_phone_number: Optional[str] = None
    recurrence_type: Optional[RecurrenceType] = RecurrenceType.NONE
    recurrence_value: Optional[str] = None
    recurrence_end_date: Optional[date] = None

class BookingCreate(BookingBase):
    pass

class Booking(BookingBase):
    id: int
    owner_id: int
    customer_id: int
    status: str
    created_at: datetime
    recurrence_id: Optional[uuid.UUID] = None

    class Config:
        orm_mode = True

class AvailabilityBase(BaseModel):
    service_id: Optional[int] = None
    date: Optional[date] = None
    start_time: time
    end_time: time
    recurrence_type: RecurrenceType = RecurrenceType.NONE
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

class OwnerUpdate(BaseModel):
    username: Optional[str] = None
    email: Optional[EmailStr] = None
    phone_number: Optional[str] = None
    language: Optional[str] = None

class SubscriptionStatus(BaseModel):
    status: str
    current_period_end: Optional[datetime]
    plan_id: str
    is_premium: bool

class AnalyticsData(BaseModel):
    monthly_bookings: List[dict]
    popular_services: List[dict]
