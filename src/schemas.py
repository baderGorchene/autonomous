from pydantic import BaseModel, EmailStr, Field, validator
from datetime import date, time, datetime
from typing import List, Optional
from .models import SubscriptionStatus, RecurrenceType

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None
    user_type: Optional[str] = None

class OwnerBase(BaseModel):
    email: EmailStr
    name: Optional[str] = None
    phone: Optional[str] = None

class OwnerCreate(OwnerBase):
    password: str = Field(..., min_length=8)

class OwnerLogin(BaseModel):
    email: EmailStr
    password: str

class OwnerUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    password: Optional[str] = Field(None, min_length=8)

class Owner(OwnerBase):
    id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
    subscription_status: SubscriptionStatus
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None

    class Config:
        from_attributes = True

class ServiceBase(BaseModel):
    name: str
    description: Optional[str] = None
    duration_minutes: int = Field(..., gt=0)
    price: float = Field(..., ge=0)
    currency: str = "USD"

class ServiceCreate(ServiceBase):
    pass

class ServiceUpdate(ServiceBase):
    name: Optional[str] = None
    duration_minutes: Optional[int] = Field(None, gt=0)
    price: Optional[float] = Field(None, ge=0)
    currency: Optional[str] = None

class Service(ServiceBase):
    id: int
    owner_id: int

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

    @validator('date', always=True)
    def validate_date_or_recurrence(cls, v, values):
        if v is None and values.get('recurrence_type') is None:
            raise ValueError("Either 'date' or 'recurrence_type' must be provided.")
        if v is not None and values.get('recurrence_type') is not None:
            raise ValueError("Cannot specify both 'date' and 'recurrence_type'.")
        return v

class AvailabilityCreate(AvailabilityBase):
    pass

class AvailabilityUpdate(AvailabilityBase):
    service_id: Optional[int] = None
    date: Optional[date] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    recurrence_type: Optional[RecurrenceType] = None
    recurrence_value: Optional[str] = None
    recurrence_start_date: Optional[date] = None
    recurrence_end_date: Optional[date] = None

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
    password: str = Field(..., min_length=8)

class CustomerLogin(BaseModel):
    email: EmailStr
    password: str

class CustomerUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    password: Optional[str] = Field(None, min_length=8)

class Customer(CustomerBase):
    id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class BookingCreate(BaseModel):
    service_id: int
    date: date
    time: time
    customer_name: str
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    is_recurring: bool = False
    recurrence_id: Optional[str] = None

class BookingUpdate(BaseModel):
    is_confirmed: Optional[bool] = None

class Booking(BookingCreate):
    id: int
    owner_id: int
    customer_id: Optional[int] = None
    created_at: datetime
    is_confirmed: bool

    class Config:
        from_attributes = True

class MonthlyBookingData(BaseModel):
    month: str
    count: int

class PopularServiceData(BaseModel):
    service_name: str
    booking_count: int