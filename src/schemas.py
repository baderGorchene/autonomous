from pydantic import BaseModel, EmailStr, Field
from datetime import datetime, time, date
from typing import List, Optional

# --- Auth & User Schemas ---
class OwnerBase(BaseModel):
    email: EmailStr
    name: Optional[str] = None
    phone: Optional[str] = None

class OwnerCreate(OwnerBase):
    password: str

class OwnerProfileUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None

class Owner(OwnerBase):
    id: int
    is_active: bool

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None

# --- Service Schemas ---
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

    class Config:
        from_attributes = True

# --- Availability Schemas ---
class AvailabilityBase(BaseModel):
    day_of_week: int  # 0=Monday, 6=Sunday
    start_time: time
    end_time: time

class AvailabilityCreate(AvailabilityBase):
    pass

class Availability(AvailabilityBase):
    id: int
    owner_id: int

    class Config:
        from_attributes = True

# --- Booking Schemas ---
class BookingBase(BaseModel):
    service_id: int
    customer_name: str
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    booking_time: datetime

class BookingCreate(BookingBase):
    pass

class Booking(BookingBase):
    id: int
    owner_id: int

    class Config:
        from_attributes = True

# --- Stripe Schemas ---
class CreateCheckoutSession(BaseModel):
    price_id: str
    success_url: str
    cancel_url: str

class StripeWebhookEvent(BaseModel):
    id: str
    object: str
    api_version: str
    created: int
    data: dict
    livemode: bool
    pending_webhooks: int
    request: Optional[dict]
    type: str

# --- Analytics Schemas ---
class BookingAnalytics(BaseModel):
    total_bookings: int

    class Config:
        from_attributes = True
