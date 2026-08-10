from typing import List, Optional
from datetime import date, time, datetime
from pydantic import BaseModel, EmailStr
from .models import RecurrenceType, SubscriptionStatus

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None
    user_type: Optional[str] = "owner" # "owner" or "customer"

# Owner Schemas
class OwnerBase(BaseModel):
    email: EmailStr
    name: Optional[str] = None
    username: Optional[str] = None
    phone_number: Optional[str] = None
    description: Optional[str] = None # New field
    city: Optional[str] = None # New field
    country: Optional[str] = None # New field

class OwnerCreate(OwnerBase):
    password: str

class Owner(OwnerBase):
    id: int
    is_active: bool

    class Config:
        orm_mode = True

# Service Schemas
class ServiceBase(BaseModel):
    name: str
    description: Optional[str] = None # New field
    duration_minutes: int
    price: float
    currency: Optional[str] = "USD"
    slug: Optional[str] = None
    category: Optional[str] = None # New field

class ServiceCreate(ServiceBase):
    pass

class Service(ServiceBase):
    id: int
    owner_id: int
    
    class Config:
        orm_mode = True

# Booking Schemas
class BookingBase(BaseModel):
    customer_name: str
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    date: date
    time: time
    is_recurring: bool = False
    recurrence_end_date: Optional[date] = None

class BookingCreate(BookingBase):
    service_id: int

class Booking(BookingBase):
    id: int
    owner_id: int
    service_id: int
    created_at: datetime

    class Config:
        orm_mode = True

class TimeSlot(BaseModel):
    time: time

    class Config:
        orm_mode = True

# Availability Schemas
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

    class Config:
        orm_mode = True

# Subscription Schemas
class SubscriptionBase(BaseModel):
    stripe_customer_id: str
    stripe_subscription_id: str
    status: SubscriptionStatus
    current_period_end: Optional[datetime] = None

class SubscriptionCreate(SubscriptionBase):
    owner_id: int

class Subscription(SubscriptionBase):
    id: int
    owner_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True

# Customer Schemas
class CustomerBase(BaseModel):
    email: EmailStr
    name: str
    phone_number: Optional[str] = None

class CustomerCreate(CustomerBase):
    password: str

class CustomerUpdate(BaseModel):
    name: Optional[str] = None
    phone_number: Optional[str] = None

class Customer(CustomerBase):
    id: int
    is_active: bool
    created_at: datetime

    class Config:
        orm_mode = True

# Review Schemas
class ReviewBase(BaseModel):
    rating: int
    comment: Optional[str] = None

class ReviewCreate(ReviewBase):
    pass

class Review(ReviewBase):
    id: int
    service_id: int
    customer_id: int
    created_at: datetime

    class Config:
        orm_mode = True
