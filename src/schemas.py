from pydantic import BaseModel, EmailStr, Field
from datetime import date, time, datetime
from typing import List, Optional
from . import models

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None

class OwnerBase(BaseModel):
    email: EmailStr
    name: Optional[str] = None
    phone: Optional[str] = None
    language: Optional[str] = "en"

class OwnerCreate(OwnerBase):
    password: str

class OwnerUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    language: Optional[str] = None
    old_password: Optional[str] = None
    new_password: Optional[str] = None

class OwnerInDB(OwnerBase):
    id: int
    is_active: bool
    stripe_customer_id: Optional[str] = None
    subscription_status: models.SubscriptionStatus
    subscription_end_date: Optional[date] = None

    class Config:
        from_attributes = True

class ServiceBase(BaseModel):
    name: str
    description: Optional[str] = None
    duration_minutes: int = Field(..., gt=0)
    price: Optional[float] = Field(None, gt=0)

class ServiceCreate(ServiceBase):
    pass

class ServiceUpdate(ServiceBase):
    name: Optional[str] = None
    duration_minutes: Optional[int] = Field(None, gt=0)
    price: Optional[float] = Field(None, gt=0)

class Service(ServiceBase):
    id: int
    owner_id: int

    class Config:
        from_attributes = True

class AvailabilityBase(BaseModel):
    service_id: Optional[int] = None # If None, applies to all services
    date: Optional[date] = None
    start_time: time
    end_time: time
    recurrence_type: Optional[models.RecurrenceType] = None
    recurrence_value: Optional[str] = None
    recurrence_start_date: Optional[date] = None
    recurrence_end_date: Optional[date] = None

class AvailabilityCreate(AvailabilityBase):
    pass

class Availability(AvailabilityBase):
    id: int
    owner_id: int

    class Config:
        from_attributes = True

class CustomerBase(BaseModel):
    email: EmailStr
    name: Optional[str] = None
    phone: Optional[str] = None

class CustomerCreate(CustomerBase):
    password: Optional[str] = None # For optional customer accounts

class CustomerLogin(BaseModel):
    email: EmailStr
    password: str

class CustomerUpdate(CustomerBase):
    email: Optional[EmailStr] = None
    old_password: Optional[str] = None
    new_password: Optional[str] = None

class CustomerInDB(CustomerBase):
    id: int
    is_active: bool

    class Config:
        from_attributes = True

class BookingBase(BaseModel):
    service_id: int
    customer_name: str
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    date: date
    time: time
    is_recurring: Optional[bool] = False
    recurrence_pattern: Optional[str] = None # e.g., 'weekly_MON,WED,FRI' or 'monthly_15'
    recurrence_end_date: Optional[date] = None

class BookingCreate(BookingBase):
    pass

class Booking(BookingBase):
    id: int
    owner_id: int
    customer_id: Optional[int] = None
    is_confirmed: bool
    created_at: datetime

    class Config:
        from_attributes = True

class BookingDisplay(Booking):
    service: Service

class MonthlyBookingData(BaseModel):
    month: str
    count: int

class PopularServiceData(BaseModel):
    service_name: str
    booking_count: int

class AnalyticsData(BaseModel):
    monthly_bookings: List[MonthlyBookingData]
    popular_services: List[PopularServiceData]

class CheckoutSessionCreate(BaseModel):
    price_id: str
    success_url: str
    cancel_url: str

class WebhookEvent(BaseModel):
    id: str
    object: str
    type: str
    data: dict

class ReviewBase(BaseModel):
    service_id: int
    rating: int = Field(..., ge=1, le=5)
    comment: Optional[str] = None
    customer_name: Optional[str] = None # For guest reviews, if customer_id is null

class ReviewCreate(ReviewBase):
    pass

class Review(ReviewBase):
    id: int
    owner_id: int
    customer_id: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True
