from pydantic import BaseModel, EmailStr, Field, root_validator
from datetime import date, time, datetime
from typing import List, Optional, Literal
from .models import RecurrenceType, SubscriptionStatus

# --- Auth Schemas ---
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None

# --- Owner Schemas ---
class OwnerBase(BaseModel):
    email: EmailStr
    name: str
    phone: Optional[str] = None

class OwnerCreate(OwnerBase):
    password: str

class OwnerUpdate(OwnerBase):
    name: str
    email: Optional[EmailStr] = None
    phone: Optional[str] = None

class OwnerInDBBase(OwnerBase):
    id: int
    subscription_status: SubscriptionStatus
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None

    class Config:
        orm_mode = True

class Owner(OwnerInDBBase):
    pass

# --- Service Schemas ---
class ServiceBase(BaseModel):
    name: str
    description: Optional[str] = None
    duration_minutes: int = Field(..., gt=0, description="Duration in minutes, must be greater than 0")
    price: int = Field(..., ge=0, description="Price in cents, must be non-negative")

class ServiceCreate(ServiceBase):
    pass

class ServiceUpdate(ServiceBase):
    name: Optional[str] = None
    duration_minutes: Optional[int] = Field(None, gt=0)
    price: Optional[int] = Field(None, ge=0)

class ServiceInDBBase(ServiceBase):
    id: int
    owner_id: int

    class Config:
        orm_mode = True

class Service(ServiceInDBBase):
    pass

# --- Availability Schemas ---
class AvailabilityBase(BaseModel):
    date: Optional[date] = None
    start_time: time
    end_time: time
    service_id: Optional[int] = None

    recurrence_type: Optional[RecurrenceType] = None
    recurrence_value: Optional[str] = None
    recurrence_start_date: Optional[date] = None
    recurrence_end_date: Optional[date] = None

    class Config:
        json_encoders = {
            time: lambda v: v.isoformat(),
            date: lambda v: v.isoformat(),
        }

class AvailabilityCreate(AvailabilityBase):
    pass

class AvailabilityUpdate(AvailabilityBase):
    pass

class AvailabilityInDBBase(AvailabilityBase):
    id: int
    owner_id: int

    class Config:
        orm_mode = True

class Availability(AvailabilityInDBBase):
    pass

# --- Booking Schemas ---
class BookingBase(BaseModel):
    customer_name: str
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    date: date
    time: time
    service_id: int

    class Config:
        json_encoders = {
            time: lambda v: v.isoformat(),
            date: lambda v: v.isoformat(),
        }

class BookingCreate(BookingBase):
    is_recurring: bool = False
    recurrence_end_date: Optional[date] = None

class BookingUpdate(BookingBase):
    customer_name: Optional[str] = None
    customer_email: Optional[EmailStr] = None
    customer_phone: Optional[str] = None
    date: Optional[date] = None
    time: Optional[time] = None
    service_id: Optional[int] = None

class BookingInDBBase(BookingBase):
    id: int
    owner_id: int
    created_at: datetime
    is_recurring: bool
    recurrence_id: Optional[str] = None

    class Config:
        orm_mode = True

class Booking(BookingInDBBase):
    pass

# --- Customer Schemas ---
class CustomerBase(BaseModel):
    email: EmailStr
    name: str
    phone: Optional[str] = None

class CustomerCreate(CustomerBase):
    password: str

class CustomerUpdate(CustomerBase):
    name: Optional[str] = None
    phone: Optional[str] = None

class CustomerInDBBase(CustomerBase):
    id: int
    created_at: datetime

    class Config:
        orm_mode = True

class Customer(CustomerInDBBase):
    pass

# --- Review Schemas ---
class ReviewBase(BaseModel):
    rating: int = Field(..., ge=1, le=5, description="Rating from 1 to 5 stars")
    comment: Optional[str] = None

class ReviewCreate(ReviewBase):
    service_id: int
    owner_id: int
    customer_id: Optional[int] = None
    customer_name: Optional[str] = None

    @root_validator(pre=True)
    def check_customer_info(cls, values):
        customer_id = values.get('customer_id')
        customer_name = values.get('customer_name')
        if customer_id is None and customer_name is None:
            raise ValueError("Either 'customer_id' or 'customer_name' must be provided for a review.")
        return values

class ReviewResponse(ReviewBase):
    id: int
    owner_id: int
    service_id: int
    customer_id: Optional[int] = None
    customer_name: str
    created_at: datetime

    class Config:
        orm_mode = True

# --- Analytics Schemas ---
class MonthlyBookingData(BaseModel):
    month: str
    count: int

class PopularServiceData(BaseModel):
    service_name: str
    booking_count: int

# --- Subscription Schemas ---
class CheckoutSessionResponse(BaseModel):
    session_id: str
    checkout_url: str

# --- Admin Schemas ---
class AdminOwnerUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    subscription_status: Optional[SubscriptionStatus] = None
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None

class AdminServiceUpdate(ServiceUpdate):
    pass

class AdminBookingUpdate(BookingUpdate):
    owner_id: Optional[int] = None
    service_id: Optional[int] = None
