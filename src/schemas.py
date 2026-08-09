from pydantic import BaseModel, EmailStr, Field
from datetime import date, time, datetime
from typing import List, Optional
from .models import RecurrenceType

# --- Owner Schemas ---
class OwnerBase(BaseModel):
    email: EmailStr
    name: str
    phone_number: Optional[str] = None

class OwnerCreate(OwnerBase):
    password: str

class OwnerUpdate(BaseModel):
    name: Optional[str] = None
    phone_number: Optional[str] = None

class Owner(OwnerBase):
    id: int
    is_active: bool
    subscription_status: str
    stripe_customer_id: Optional[str] = None

    class Config:
        orm_mode = True

# --- Service Schemas ---
class ServiceBase(BaseModel):
    name: str
    description: Optional[str] = None
    duration_minutes: int = Field(..., gt=0)
    price: int = Field(..., ge=0) # Price in cents

class ServiceCreate(ServiceBase):
    pass

class ServiceUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    duration_minutes: Optional[int] = Field(None, gt=0)
    price: Optional[int] = Field(None, ge=0)

class Service(ServiceBase):
    id: int
    owner_id: int

    class Config:
        orm_mode = True

# --- Customer Schemas ---
class CustomerBase(BaseModel):
    name: str
    email: EmailStr
    phone_number: Optional[str] = None

class CustomerCreate(CustomerBase):
    pass

class Customer(CustomerBase):
    id: int
    created_at: datetime

    class Config:
        orm_mode = True

# --- Booking Schemas ---
class BookingBase(BaseModel):
    customer_name: str
    customer_email: EmailStr
    customer_phone_number: Optional[str] = None
    date: date
    time: time

class BookingCreate(BookingBase):
    service_id: int
    # Fields for recurring bookings
    is_recurring: bool = False
    recurrence_type: RecurrenceType = RecurrenceType.NONE
    recurrence_value: Optional[str] = None # e.g., 'MON,WED,FRI' or '15'
    recurrence_end_date: Optional[date] = None

class BookingResponse(BookingBase):
    id: int
    owner_id: int
    service_id: int
    customer_id: Optional[int] = None # Optional link to a Customer account
    # Fields for recurring bookings
    is_recurring: bool
    recurrence_id: Optional[str] = None
    recurrence_type: RecurrenceType
    recurrence_value: Optional[str] = None
    recurrence_end_date: Optional[date] = None

    class Config:
        orm_mode = True

class BookingDisplay(BookingResponse):
    service: Service
    customer: Optional[Customer] = None # Include customer details if linked

class BookingAnalytics(BaseModel):
    month: str
    count: int

class PopularServiceAnalytics(BaseModel):
    service_name: str
    booking_count: int

# --- Availability Schemas ---
class AvailabilityBase(BaseModel):
    start_time: time
    end_time: time
    service_id: Optional[int] = None # If None, applies to all services

class AvailabilityCreate(AvailabilityBase):
    date: Optional[date] = None # Specific date for one-off, None for recurring
    recurrence_type: RecurrenceType = RecurrenceType.NONE
    recurrence_value: Optional[str] = None
    recurrence_start_date: Optional[date] = None
    recurrence_end_date: Optional[date] = None

class AvailabilityUpdate(BaseModel):
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    service_id: Optional[int] = None
    date: Optional[date] = None
    recurrence_type: Optional[RecurrenceType] = None
    recurrence_value: Optional[str] = None
    recurrence_start_date: Optional[date] = None
    recurrence_end_date: Optional[date] = None

class Availability(AvailabilityBase):
    id: int
    owner_id: int
    date: Optional[date] = None
    recurrence_type: RecurrenceType
    recurrence_value: Optional[str] = None
    recurrence_start_date: Optional[date] = None
    recurrence_end_date: Optional[date] = None

    class Config:
        orm_mode = True

# --- Token Schemas ---
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None

# --- Stripe Schemas ---
class CreateCheckoutSessionResponse(BaseModel):
    session_id: str
    public_key: str

# --- Admin Panel Schemas ---
class AdminOwnerUpdate(OwnerUpdate):
    email: Optional[EmailStr] = None
    is_active: Optional[bool] = None
    subscription_status: Optional[str] = None

class AdminServiceUpdate(ServiceUpdate):
    owner_id: Optional[int] = None

class AdminBookingUpdate(BaseModel):
    customer_name: Optional[str] = None
    customer_email: Optional[EmailStr] = None
    customer_phone_number: Optional[str] = None
    date: Optional[date] = None
    time: Optional[time] = None
    is_recurring: Optional[bool] = None
    recurrence_type: Optional[RecurrenceType] = None
    recurrence_value: Optional[str] = None
    recurrence_end_date: Optional[date] = None
