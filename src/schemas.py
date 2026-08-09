from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import date, time, datetime
from .models import RecurrenceType

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    owner_id: Optional[int] = None

class OwnerBase(BaseModel):
    email: EmailStr
    name: str
    phone: Optional[str] = None
    locale: str = "en"

class OwnerCreate(OwnerBase):
    password: str

class OwnerUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    locale: Optional[str] = None

class OwnerInDB(OwnerBase):
    id: int
    hashed_password: str
    is_premium: bool
    stripe_customer_id: Optional[str]
    stripe_subscription_id: Optional[str]

    class Config:
        from_attributes = True

class ServiceBase(BaseModel):
    name: str
    description: Optional[str] = None
    duration_minutes: int = Field(..., gt=0)
    price: int = Field(..., ge=0) # Price in smallest currency unit (e.g., cents)

class ServiceCreate(ServiceBase):
    pass

class ServiceUpdate(ServiceBase):
    name: Optional[str] = None
    description: Optional[str] = None
    duration_minutes: Optional[int] = None
    price: Optional[int] = None

class Service(ServiceBase):
    id: int
    owner_id: int

    class Config:
        from_attributes = True

class AvailabilityBase(BaseModel):
    start_time: time
    end_time: time
    service_id: Optional[int] = None # If None, applies to all services

class AvailabilityCreate(AvailabilityBase):
    date: Optional[date] = None # Specific date for one-off
    recurrence_type: RecurrenceType = RecurrenceType.NONE
    recurrence_value: Optional[str] = None # e.g., "MON,TUE,WED" or "15"
    recurrence_end_date: Optional[date] = None

class AvailabilityUpdate(AvailabilityBase):
    date: Optional[date] = None
    recurrence_type: Optional[RecurrenceType] = None
    recurrence_value: Optional[str] = None
    recurrence_end_date: Optional[date] = None

class Availability(AvailabilityBase):
    id: int
    owner_id: int
    date: Optional[date]
    recurrence_type: RecurrenceType
    recurrence_value: Optional[str]
    recurrence_end_date: Optional[date]

    class Config:
        from_attributes = True

class BookingBase(BaseModel):
    service_id: int
    customer_name: str
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    date: date
    time: time

class BookingCreate(BookingBase):
    pass

class Booking(BookingBase):
    id: int
    owner_id: int
    status: str
    created_at: datetime

    class Config:
        from_attributes = True

class MonthlyBookingData(BaseModel):
    month: str
    count: int

class PopularServiceData(BaseModel):
    service_name: str
    booking_count: int

class AnalyticsData(BaseModel):
    monthly_bookings: List[MonthlyBookingData]
    popular_services: List[PopularServiceData]

class StripeCheckoutSession(BaseModel):
    session_id: str
    checkout_url: str

class WebhookEvent(BaseModel):
    id: str
    object: str
    api_version: str
    created: int
    data: dict
    livemode: bool
    pending_webhooks: int
    request: Optional[dict] = None
    type: str