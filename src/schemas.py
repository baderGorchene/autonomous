from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from typing import List, Optional

# Admin Schemas
class AdminBase(BaseModel):
    email: EmailStr
    name: Optional[str] = None

class AdminCreate(AdminBase):
    password: str

class Admin(AdminBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

# Owner Schemas (relevant for admin updates)
class OwnerBase(BaseModel):
    name: str
    email: EmailStr
    phone: Optional[str] = None

class OwnerCreate(OwnerBase):
    password: str
    subscription_status: Optional[str] = None

class OwnerProfileUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None

class OwnerAdminUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    subscription_status: Optional[str] = None
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None

class Owner(OwnerBase):
    id: int
    created_at: datetime
    updated_at: datetime
    subscription_status: str = "free"
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None
    is_active: bool = True

    model_config = {"from_attributes": True}

# Service Schemas
class ServiceBase(BaseModel):
    name: str
    description: Optional[str] = None
    duration_minutes: int = Field(..., gt=0, description="Duration in minutes, must be positive.")
    price: int = Field(..., ge=0, description="Price in smallest currency unit (e.g., cents), must be non-negative.")

class ServiceCreate(ServiceBase):
    pass

class Service(ServiceBase):
    id: int
    owner_id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

# Availability Schemas
class AvailabilityBase(BaseModel):
    day_of_week: int = Field(..., ge=0, le=6, description="Day of the week (0=Monday, 6=Sunday).")
    start_time: str = Field(..., pattern=r"^(?:2[0-3]|[01]?[0-9]):[0-5][0-9]$", description="Start time in HH:MM format.")
    end_time: str = Field(..., pattern=r"^(?:2[0-3]|[01]?[0-9]):[0-5][0-9]$", description="End time in HH:MM format.")

class AvailabilityCreate(AvailabilityBase):
    pass

class Availability(AvailabilityBase):
    id: int
    service_id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

# Booking Schemas
class BookingBase(BaseModel):
    customer_name: str
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    booking_time: datetime

class BookingCreate(BookingBase):
    service_id: int

class Booking(BookingBase):
    id: int
    owner_id: int
    service_id: int
    created_at: datetime
    updated_at: datetime
    service: Service

    model_config = {"from_attributes": True}

# Token Schema
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None

# Analytics Schemas
class MonthlyBookingData(BaseModel):
    month: str
    count: int

class PopularServiceData(BaseModel):
    service_name: str
    count: int

class OwnerAnalytics(BaseModel):
    total_bookings: int
    monthly_bookings: List[MonthlyBookingData]
    popular_services: List[PopularServiceData]
