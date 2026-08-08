from pydantic import BaseModel, EmailStr, Field
from datetime import datetime, date
from typing import List, Optional

# --- Owner Schemas ---
class OwnerBase(BaseModel):
    email: EmailStr
    name: str
    phone: Optional[str] = None
    locale: Optional[str] = "en"

class OwnerCreate(OwnerBase):
    password: str

class OwnerUpdate(OwnerBase):
    email: Optional[EmailStr] = None
    name: Optional[str] = None
    phone: Optional[str] = None
    locale: Optional[str] = None

class OwnerInDB(OwnerBase):
    id: int
    is_active: bool

    class Config:
        from_attributes = True

class Owner(OwnerInDB):
    pass

# --- Token Schemas ---
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None

# --- Service Schemas ---
class ServiceBase(BaseModel):
    name: str
    description: Optional[str] = None
    duration_minutes: int = Field(..., gt=0, description="Duration in minutes, must be greater than 0")
    price: float = Field(..., gt=0, description="Price of the service, must be greater than 0")

class ServiceCreate(ServiceBase):
    pass

class ServiceUpdate(ServiceBase):
    name: Optional[str] = None
    description: Optional[str] = None
    duration_minutes: Optional[int] = Field(None, gt=0, description="Duration in minutes, must be greater than 0")
    price: Optional[float] = Field(None, gt=0, description="Price of the service, must be greater than 0")


class ServiceInDB(ServiceBase):
    id: int
    owner_id: int

    class Config:
        from_attributes = True

# --- Availability Slot Schemas ---
class AvailabilitySlotBase(BaseModel):
    day_of_week: int = Field(..., ge=0, le=6, description="Day of week (0=Monday, 6=Sunday)")
    start_time: str = Field(..., pattern=r"^(?:2[0-3]|[01]?[0-9]):(?:[0-5]?[0-9])$", description="Start time in HH:MM format")
    end_time: str = Field(..., pattern=r"^(?:2[0-3]|[01]?[0-9]):(?:[0-5]?[0-9])$", description="End time in HH:MM format")

class AvailabilitySlotCreate(AvailabilitySlotBase):
    service_id: int

class AvailabilitySlotInDB(AvailabilitySlotBase):
    id: int
    service_id: int

    class Config:
        from_attributes = True

# --- Booking Schemas ---
class BookingBase(BaseModel):
    customer_name: str
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    booking_time: datetime

class BookingCreate(BookingBase):
    service_id: int
    owner_id: int # This will be derived from the owner's public page, or current owner for dashboard booking

class PublicBookingCreate(BookingBase):
    service_id: int
    # owner_id is derived from path parameter

class BookingInDB(BookingBase):
    id: int
    owner_id: int
    service_id: int
    status: str
    created_at: datetime

    class Config:
        from_attributes = True

class BookingDisplay(BookingInDB):
    service_name: str
    service_price: float
    owner_name: str

class BookingConfirmation(BaseModel):
    message: str
    booking_id: int
    owner_name: str
    service_name: str
    booking_time: datetime
    customer_name: str
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    service_price: float

# --- Dashboard Schemas ---
class DashboardBooking(BaseModel):
    id: int
    customer_name: str
    customer_email: str
    customer_phone: Optional[str]
    booking_time: datetime
    service_name: str
    service_duration: int
    status: str

    class Config:
        from_attributes = True

class DashboardService(BaseModel):
    id: int
    name: str
    duration_minutes: int
    price: float
    description: Optional[str]

    class Config:
        from_attributes = True

class DashboardAvailabilitySlot(BaseModel):
    id: int
    day_of_week: int
    start_time: str
    end_time: str
    service_id: int

    class Config:
        from_attributes = True

# --- Payment Schemas ---
class PaymentIntentCreate(BaseModel):
    booking_id: int

class PaymentResponse(BaseModel):
    client_secret: str
    publishable_key: str
    booking_id: int

    class Config:
        from_attributes = True

class PaymentWebhookEvent(BaseModel):
    id: str
    object: str
    api_version: str
    created: int
    data: dict
    livemode: bool
    pending_webhooks: int
    request: Optional[dict] = None
    type: str
