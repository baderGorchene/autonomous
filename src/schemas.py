from pydantic import BaseModel, EmailStr, Field
from datetime import date, time, datetime
from typing import List, Optional
from .models import RecurrenceType, SubscriptionStatus

# --- Owner Schemas ---
class OwnerBase(BaseModel):
    username: str
    email: EmailStr
    full_name: Optional[str] = None
    phone_number: Optional[str] = None

class OwnerCreate(OwnerBase):
    password: str

class OwnerUpdate(BaseModel):
    full_name: Optional[str] = None
    phone_number: Optional[str] = None
    email: Optional[EmailStr] = None

class OwnerInDB(OwnerBase):
    id: int
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None

# --- Service Schemas ---
class ServiceBase(BaseModel):
    name: str
    description: Optional[str] = None
    duration_minutes: int = Field(..., gt=0)
    price: float = Field(..., gt=0)
    currency: str = "USD"

class ServiceCreate(ServiceBase):
    pass

class ServiceUpdate(ServiceBase):
    name: Optional[str] = None
    description: Optional[str] = None
    duration_minutes: Optional[int] = None
    price: Optional[float] = None
    currency: Optional[str] = None

class Service(ServiceBase):
    id: int
    owner_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# --- Availability Schemas ---
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
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# --- Customer Schemas ---
class CustomerBase(BaseModel):
    email: EmailStr
    full_name: Optional[str] = None
    phone_number: Optional[str] = None

class CustomerCreate(CustomerBase):
    password: Optional[str] = None

class CustomerUpdate(BaseModel):
    full_name: Optional[str] = None
    phone_number: Optional[str] = None
    email: Optional[EmailStr] = None

class CustomerInDB(CustomerBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# --- Booking Schemas ---
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
    customer_id: Optional[int] = None
    is_confirmed: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# --- Subscription Schemas ---
class SubscriptionBase(BaseModel):
    stripe_customer_id: str
    stripe_subscription_id: str
    status: SubscriptionStatus
    current_period_end: datetime

class Subscription(SubscriptionBase):
    id: int
    owner_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# --- Analytics Schemas ---
class MonthlyBookingsData(BaseModel):
    month: str
    count: int

class PopularServiceData(BaseModel):
    service_name: str
    booking_count: int

# --- Review Schemas (NEW) ---
class ReviewBase(BaseModel):
    rating: int = Field(..., ge=1, le=5, description="Rating from 1 to 5 stars")
    comment: Optional[str] = Field(None, max_length=500, description="Optional review comment")

class ReviewCreate(ReviewBase):
    pass

class Review(ReviewBase):
    id: int
    service_id: int
    customer_id: int
    owner_id: int
    created_at: datetime

    class Config:
        from_attributes = True