from pydantic import BaseModel, EmailStr, Field
from datetime import date, time, datetime
from typing import Optional, List
from .models import RecurrenceType, SubscriptionStatus 

class OwnerBase(BaseModel):
    email: EmailStr
    name: str
    phone: Optional[str] = None
    currency: Optional[str] = "USD"
    locale: Optional[str] = "en"

class OwnerCreate(OwnerBase):
    password: str

class OwnerLogin(BaseModel):
    email: EmailStr
    password: str

class OwnerUpdate(OwnerBase):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    currency: Optional[str] = None
    locale: Optional[str] = None

class OwnerResponse(OwnerBase):
    id: int
    is_premium: bool
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None
    subscription_status: Optional[SubscriptionStatus] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True

class ServiceBase(BaseModel):
    name: str
    description: Optional[str] = None
    duration_minutes: int = Field(..., gt=0, description="Duration in minutes, must be greater than 0")
    price: int = Field(..., ge=0, description="Price in cents, must be non-negative")

class ServiceCreate(ServiceBase):
    pass

class ServiceUpdate(ServiceBase):
    name: Optional[str] = None
    description: Optional[str] = None
    duration_minutes: Optional[int] = Field(None, gt=0)
    price: Optional[int] = Field(None, ge=0)

class ServiceResponse(ServiceBase):
    id: int
    owner_id: int

    class Config:
        orm_mode = True

class AvailabilityBase(BaseModel):
    date: Optional[date] = None 
    start_time: time
    end_time: time
    recurrence_type: Optional[RecurrenceType] = None
    recurrence_value: Optional[str] = None 
    recurrence_start_date: Optional[date] = None
    recurrence_end_date: Optional[date] = None

class AvailabilityCreate(AvailabilityBase):
    service_id: Optional[int] = None 

class AvailabilityUpdate(AvailabilityBase):
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    date: Optional[date] = None
    recurrence_type: Optional[RecurrenceType] = None
    recurrence_value: Optional[str] = None
    recurrence_start_date: Optional[date] = None
    recurrence_end_date: Optional[date] = None

class AvailabilityResponse(AvailabilityBase):
    id: int
    owner_id: int
    service_id: Optional[int] = None

    class Config:
        orm_mode = True

class BookingBase(BaseModel):
    customer_name: str
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    date: date
    time: time

class BookingCreate(BookingBase):
    service_id: int
    is_recurring_booking: bool = False

class BookingResponse(BookingBase):
    id: int
    owner_id: int
    service_id: int
    status: str
    created_at: datetime
    updated_at: datetime
    is_recurring_booking: bool
    original_booking_id: Optional[int] = None

    class Config:
        orm_mode = True

class BookingStatusUpdate(BaseModel):
    status: str 

class CustomerBase(BaseModel):
    email: EmailStr
    name: str
    phone: Optional[str] = None

class CustomerCreate(CustomerBase):
    password: str 

class CustomerLogin(BaseModel):
    email: EmailStr
    password: str

class CustomerUpdate(CustomerBase):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None

class CustomerResponse(CustomerBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True

class SubscriptionResponse(BaseModel):
    id: int
    owner_id: int
    stripe_customer_id: str
    stripe_subscription_id: str
    status: SubscriptionStatus
    current_period_end: datetime
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None
    user_type: Optional[str] = None # Added user_type

class MonthlyBookingsData(BaseModel):
    month: str
    count: int

class PopularServiceData(BaseModel):
    service_name: str
    booking_count: int

class ReviewBase(BaseModel):
    rating: int = Field(..., ge=1, le=5, description="Rating from 1 to 5 stars")
    comment: Optional[str] = Field(None, max_length=500, description="Optional comment for the review")

class ReviewCreate(ReviewBase):
    pass

class ReviewResponse(ReviewBase):
    id: int
    service_id: int
    customer_id: int
    created_at: datetime
    updated_at: datetime
    customer_name: Optional[str] = None 

    class Config:
        orm_mode = True
