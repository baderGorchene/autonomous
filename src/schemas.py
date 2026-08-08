from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from typing import List, Optional

# --- Owner Schemas ---
class OwnerBase(BaseModel):
    email: EmailStr
    full_name: str
    phone_number: Optional[str] = None

class OwnerCreate(OwnerBase):
    password: str

class OwnerLogin(BaseModel):
    email: EmailStr
    password: str

class OwnerUpdate(BaseModel):
    full_name: Optional[str] = None
    phone_number: Optional[str] = None

class OwnerInDB(OwnerBase):
    id: int
    is_active: bool
    created_at: datetime
    stripe_customer_id: Optional[str] = None
    is_premium: bool = False

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
    duration_minutes: int = Field(..., gt=0)
    price: int = Field(..., ge=0) # Price in cents

class ServiceCreate(ServiceBase):
    pass

class Service(ServiceBase):
    id: int
    owner_id: int
    is_active: bool

    class Config:
        from_attributes = True

# --- Availability Schemas ---
class AvailabilityBase(BaseModel):
    day_of_week: int = Field(..., ge=0, le=6)
    start_time: str = Field(..., pattern=r"^\d{2}:\d{2}$")
    end_time: str = Field(..., pattern=r"^\d{2}:\d{2}$")

class AvailabilityCreate(AvailabilityBase):
    pass

class Availability(AvailabilityBase):
    id: int
    owner_id: int

    class Config:
        from_attributes = True

# --- Booking Schemas ---
class BookingBase(BaseModel):
    customer_name: str
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    booking_date: str # YYYY-MM-DD
    start_time: str # HH:MM
    service_id: int

class BookingCreate(BookingBase):
    pass

class Booking(BookingBase):
    id: int
    owner_id: int
    end_time: str
    status: str
    created_at: datetime

    class Config:
        from_attributes = True

class BookingDisplay(BaseModel):
    id: int
    customer_name: str
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    booking_date: str
    start_time: str
    end_time: str
    service_name: str
    service_duration: int
    service_price: float # For display, convert cents to currency
    status: str
    created_at: datetime

    class Config:
        from_attributes = True

# --- Stripe Schemas ---
class CreateCheckoutSessionRequest(BaseModel):
    pass

class StripeWebhookEvent(BaseModel):
    id: str
    object: str
    api_version: str
    created: int
    data: dict
    livemode: bool
    pending_webhooks: int
    request: Optional[dict] = None
    type: str
