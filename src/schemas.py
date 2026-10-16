from pydantic import BaseModel, EmailStr, Field
from typing import List, Optional, Dict, Any
from datetime import date, time, datetime
from enum import Enum

class RecurrenceType(str, Enum):
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    owner_id: Optional[str] = None

class OwnerBase(BaseModel):
    email: EmailStr
    name: str = Field(..., min_length=1, max_length=100)
    phone: Optional[str] = None
    currency: Optional[str] = "USD"
    business_name: Optional[str] = None
    slug: Optional[str] = None

class OwnerCreate(OwnerBase):
    password: Optional[str] = "password123"
    services: Optional[List[Dict[str, Any]]] = None
    availability: Optional[List[Dict[str, Any]]] = None

class OwnerUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    phone: Optional[str] = None
    currency: Optional[str] = None
    business_name: Optional[str] = None
    slug: Optional[str] = None

OwnerProfileUpdate = OwnerUpdate

class Owner(OwnerBase):
    id: int
    is_active: bool
    is_premium: bool = False
    is_admin: bool = False
    name_slug: Optional[str] = None
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None

    class Config:
        from_attributes = True
        orm_mode = True

class ServiceBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    duration_minutes: int = Field(..., gt=0)
    price: float = Field(..., ge=0.0)

class ServiceCreate(ServiceBase):
    pass

class ServiceUpdate(ServiceBase):
    name: str = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    duration_minutes: Optional[int] = Field(None, gt=0)
    price: Optional[float] = Field(None, ge=0.0)

class Service(ServiceBase):
    id: int
    owner_id: int

    class Config:
        orm_mode = True

class BookingBase(BaseModel):
    service_id: Optional[int] = 1
    service_name: Optional[str] = None
    customer_name: str = Field(..., min_length=1, max_length=100)
    customer_email: EmailStr
    customer_phone: Optional[str] = Field(None, min_length=1, max_length=30)
    date: Optional[date] = None
    time: Optional[time] = None
    booking_time: Optional[datetime] = None
    notes: Optional[str] = Field(None, max_length=500)
    owner_id: Optional[int] = None
    
    # For recurring bookings
    recurrence_type: Optional[RecurrenceType] = None
    recurrence_value: Optional[str] = Field(None, max_length=50) # e.g., "MON,WED,FRI" for weekly, "15" for monthly
    recurrence_end_date: Optional[date] = None

class BookingCreate(BookingBase):
    pass

class Booking(BookingBase):
    id: int
    owner_id: int
    created_at: datetime
    customer_id: Optional[int] # Link to customer account if they booked while logged in

    class Config:
        orm_mode = True

class AvailabilityBase(BaseModel):
    service_id: Optional[int] = None # If None, applies to all services for the owner
    date: Optional[date] = None # Specific date for one-off availability
    start_time: time
    end_time: time
    
    # For recurring availability
    recurrence_type: Optional[RecurrenceType] = None
    recurrence_value: Optional[str] = Field(None, max_length=50) # e.g., "MON,TUE" or "15"
    recurrence_start_date: Optional[date] = None
    recurrence_end_date: Optional[date] = None

class AvailabilityCreate(AvailabilityBase):
    pass

class Availability(AvailabilityBase):
    id: int
    owner_id: int

    class Config:
        orm_mode = True

class AnalyticsData(BaseModel):
    monthly_bookings: List[Dict[str, Any]]
    popular_services: List[Dict[str, Any]]

class CustomerBase(BaseModel):
    email: EmailStr
    name: str = Field(..., min_length=1, max_length=100)
    phone: str = Field(..., min_length=10, max_length=20)

class CustomerCreate(CustomerBase):
    password: str = Field(..., min_length=8)

class CustomerUpdate(CustomerBase):
    name: str = Field(..., min_length=1, max_length=100)
    phone: str = Field(..., min_length=10, max_length=20)

class Customer(CustomerBase):
    id: int
    is_active: bool = True

    class Config:
        orm_mode = True

class ReviewBase(BaseModel):
    service_id: int
    rating: int = Field(..., ge=1, le=5)
    comment: Optional[str] = Field(None, max_length=1000)

class ReviewCreate(ReviewBase):
    pass

class Review(ReviewBase):
    id: int
    customer_id: int
    created_at: datetime

    class Config:
        orm_mode = True
