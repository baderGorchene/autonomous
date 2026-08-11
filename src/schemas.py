from pydantic import BaseModel, EmailStr, Field
from datetime import date, time, datetime
from typing import Optional, List
from .models import RecurrenceType

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None

class OwnerBase(BaseModel):
    email: EmailStr
    name: str
    phone: Optional[str] = None

class OwnerCreate(OwnerBase):
    password: str

class Owner(OwnerBase):
    id: int
    is_active: bool
    class Config:
        from_attributes = True

class ServiceBase(BaseModel):
    name: str
    description: Optional[str] = None
    duration_minutes: int = Field(..., gt=0)
    price: int = Field(..., ge=0)

class ServiceCreate(ServiceBase):
    pass

class Service(ServiceBase):
    id: int
    owner_id: int
    class Config:
        from_attributes = True

class CustomerBase(BaseModel):
    name: str
    email: Optional[EmailStr] = None
    phone: Optional[str] = None

class CustomerCreate(CustomerBase):
    password: Optional[str] = None

class Customer(CustomerBase):
    id: int
    class Config:
        from_attributes = True

class BookingBase(BaseModel):
    service_id: int
    customer_name: str
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    date: date
    time: time
    is_recurring: bool = False
    recurrence_id: Optional[str] = None

class BookingCreate(BookingBase):
    customer_id: Optional[int] = None

class Booking(BookingBase):
    id: int
    owner_id: int
    is_confirmed: bool
    class Config:
        from_attributes = True

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
        from_attributes = True

class SubscriptionBase(BaseModel):
    status: str
    current_period_end: Optional[datetime] = None

class SubscriptionCreate(SubscriptionBase):
    owner_id: int
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None

class Subscription(SubscriptionBase):
    id: int
    owner_id: int
    class Config:
        from_attributes = True

class ReviewBase(BaseModel):
    service_id: int
    customer_id: int
    rating: int = Field(..., ge=1, le=5)
    comment: Optional[str] = None

class ReviewCreate(ReviewBase):
    pass

class Review(ReviewBase):
    id: int
    created_at: datetime
    class Config:
        from_attributes = True

class MonthlyBookingsData(BaseModel):
    month: str
    count: int

class PopularServiceData(BaseModel):
    service_name: str
    booking_count: int