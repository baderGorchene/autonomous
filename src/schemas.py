from pydantic import BaseModel, EmailStr
from datetime import date, time, datetime
from typing import List, Optional, Dict, Any

# Owner Schemas
class OwnerBase(BaseModel):
    email: EmailStr
    name: Optional[str] = None
    phone_number: Optional[str] = None

class OwnerCreate(OwnerBase):
    password: str

class OwnerUpdate(BaseModel):
    name: Optional[str] = None
    phone_number: Optional[str] = None
    password: Optional[str] = None # For password change

class OwnerResponse(OwnerBase):
    id: int
    is_active: bool
    bookings_count: int
    subscription_status: str

    class Config:
        orm_mode = True

# Service Schemas
class ServiceBase(BaseModel):
    name: str
    description: Optional[str] = None
    duration_minutes: int
    price: int # Price in cents

class ServiceCreate(ServiceBase):
    pass

class ServiceUpdate(ServiceBase):
    name: Optional[str] = None
    description: Optional[str] = None
    duration_minutes: Optional[int] = None
    price: Optional[int] = None

class ServiceResponse(ServiceBase):
    id: int
    owner_id: int
    class Config:
        orm_mode = True

# Availability Schemas
class AvailabilityBase(BaseModel):
    service_id: Optional[int] = None # If None, applies to all services
    date: Optional[date] = None # For one-off availability
    start_time: time
    end_time: time
    recurrence_type: Optional[str] = None # e.g., "DAILY", "WEEKLY", "MONTHLY"
    recurrence_value: Optional[str] = None # e.g., "MON,WED,FRI" or "15"
    recurrence_start_date: Optional[date] = None
    recurrence_end_date: Optional[date] = None

class AvailabilityCreate(AvailabilityBase):
    pass

class AvailabilityResponse(AvailabilityBase):
    id: int
    owner_id: int
    class Config:
        orm_mode = True

# Customer Schemas
class CustomerBase(BaseModel):
    email: EmailStr
    name: Optional[str] = None
    phone_number: Optional[str] = None

class CustomerCreate(CustomerBase):
    password: Optional[str] = None # Only required if creating an account

class CustomerResponse(CustomerBase):
    id: int
    owner_id: int
    class Config:
        orm_mode = True

# Booking Schemas
class BookingCreate(BaseModel):
    service_id: int
    date: date
    time: time
    customer_name: str
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    is_recurring: bool = False
    recurrence_id: Optional[str] = None # For associating multiple recurring bookings
    customer_id: Optional[int] = None # If an existing customer is booking
    create_customer_account: bool = False # If customer wants to create an account
    customer_password: Optional[str] = None # Password for new customer account

class BookingResponse(BaseModel):
    id: int
    service_id: int
    owner_id: int
    customer_id: Optional[int] = None # New
    date: date
    time: time
    customer_name: str
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    status: str
    is_recurring: bool
    recurrence_id: Optional[str] = None
    service: ServiceResponse # Nested service details
    customer: Optional[CustomerResponse] = None # Nested customer details

    class Config:
        orm_mode = True

# Token Schemas
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None # For owner email

# Admin Schemas
class AdminOwnerUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone_number: Optional[str] = None
    is_active: Optional[bool] = None
    subscription_status: Optional[str] = None # 'free', 'premium', 'canceled'

class AdminServiceUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    duration_minutes: Optional[int] = None
    price: Optional[int] = None

class AdminBookingUpdate(BaseModel):
    status: Optional[str] = None # e.g., "confirmed", "canceled"

# Payment Schemas
class PaymentResponse(BaseModel):
    id: int
    owner_id: int
    stripe_charge_id: str
    amount: int
    currency: str
    status: str
    created_at: date

    class Config:
        orm_mode = True

# Analytics Schemas
class MonthlyBookingsData(BaseModel):
    month: str
    count: int

class PopularServicesData(BaseModel):
    service_name: str
    booking_count: int
