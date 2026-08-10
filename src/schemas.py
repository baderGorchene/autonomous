from pydantic import BaseModel, EmailStr, Field, validator
from typing import List, Optional, Dict
from datetime import date, time, datetime
from .models import RecurrenceType, SubscriptionStatus

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None

class OwnerBase(BaseModel):
    email: EmailStr
    name: Optional[str] = None
    phone: Optional[str] = None
    locale: str = "en"

class OwnerCreate(OwnerBase):
    password: str = Field(..., min_length=8)

class OwnerUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    locale: Optional[str] = None

class OwnerInDB(OwnerBase):
    id: int
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime]
    stripe_customer_id: Optional[str] = None
    subscription_status: SubscriptionStatus = SubscriptionStatus.INACTIVE
    stripe_subscription_id: Optional[str] = None

    class Config:
        orm_mode = True

class Owner(OwnerInDB):
    pass

class ServiceBase(BaseModel):
    name: str = Field(..., min_length=1)
    description: Optional[str] = None
    duration_minutes: int = Field(..., gt=0)
    price: int = Field(0, ge=0)

class ServiceCreate(ServiceBase):
    pass

class ServiceUpdate(ServiceBase):
    name: Optional[str] = None
    duration_minutes: Optional[int] = None
    price: Optional[int] = None

class Service(ServiceBase):
    id: int
    owner_id: int

    class Config:
        orm_mode = True

class AvailabilityBase(BaseModel):
    start_time: time
    end_time: time

class AvailabilityCreate(AvailabilityBase):
    date: Optional[date] = None
    service_id: Optional[int] = None
    recurrence_type: Optional[RecurrenceType] = None
    recurrence_value: Optional[str] = None
    recurrence_start_date: Optional[date] = None
    recurrence_end_date: Optional[date] = None

    @validator('recurrence_type', always=True)
    def validate_recurrence_fields(cls, v, values):
        if v:
            if not values.get('recurrence_start_date'):
                raise ValueError('recurrence_start_date is required for recurring availability')
        return v

class Availability(AvailabilityCreate):
    id: int
    owner_id: int

    class Config:
        orm_mode = True

class CustomerBase(BaseModel):
    email: EmailStr
    phone: Optional[str] = None
    name: Optional[str] = None

class CustomerCreate(CustomerBase):
    password: str = Field(..., min_length=8)

class CustomerUpdate(CustomerBase):
    email: Optional[EmailStr] = None

class CustomerInDB(CustomerBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        orm_mode = True

class Customer(CustomerInDB):
    pass

class BookingBase(BaseModel):
    service_id: int
    customer_name: str = Field(..., min_length=1)
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    date: date
    time: time
    
class BookingCreate(BookingBase):
    is_recurring: bool = False
    recurrence_id: Optional[str] = None
    recurrence_type: Optional[RecurrenceType] = None
    recurrence_value: Optional[str] = None
    recurrence_end_date: Optional[date] = None

    @validator('recurrence_type', 'recurrence_value', 'recurrence_end_date', always=True)
    def validate_recurring_fields(cls, v, values):
        if values.get('is_recurring'):
            if not v:
                for field_name in ['recurrence_type', 'recurrence_value', 'recurrence_end_date']:
                    if field_name not in values or values[field_name] is None:
                        raise ValueError(f'{field_name} is required for recurring bookings')
        return v

class Booking(BookingBase):
    id: int
    owner_id: int
    customer_id: Optional[int] = None
    is_confirmed: bool
    created_at: datetime
    
    is_recurring: bool
    recurrence_id: Optional[str]
    parent_booking_id: Optional[int]

    class Config:
        orm_mode = True

class ReviewBase(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    comment: Optional[str] = Field(None, max_length=500)

class ReviewCreate(ReviewBase):
    customer_name: Optional[str] = None

class Review(ReviewBase):
    id: int
    owner_id: int
    customer_id: Optional[int]
    created_at: datetime

    class Config:
        orm_mode = True

class SubscriptionBase(BaseModel):
    stripe_subscription_id: str
    stripe_customer_id: str
    status: SubscriptionStatus
    current_period_end: datetime

class SubscriptionCreate(SubscriptionBase):
    pass

class Subscription(SubscriptionBase):
    id: int
    owner_id: int
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        orm_mode = True

class MonthlyBookingData(BaseModel):
    month: str
    count: int

class PopularServiceData(BaseModel):
    service_name: str
    booking_count: int

class DashboardAnalytics(BaseModel):
    monthly_bookings: List[MonthlyBookingData]
    popular_services: List[PopularServiceData]

class AdminOwnerUpdate(OwnerUpdate):
    is_active: Optional[bool] = None
    subscription_status: Optional[SubscriptionStatus] = None
    stripe_subscription_id: Optional[str] = None
    stripe_customer_id: Optional[str] = None