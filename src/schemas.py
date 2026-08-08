from pydantic import BaseModel, EmailStr
from typing import List, Optional
from datetime import datetime, date
import uuid

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None

class OwnerBase(BaseModel):
    email: EmailStr
    name: str
    phone: Optional[str] = None
    locale: str = "en"

class OwnerCreate(OwnerBase):
    password: str

class OwnerLogin(BaseModel):
    email: EmailStr
    password: str

class OwnerUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    locale: Optional[str] = None

class OwnerInDBBase(OwnerBase):
    id: int
    is_active: bool
    stripe_customer_id: Optional[str] = None

    class Config:
        from_attributes = True

class Owner(OwnerInDBBase):
    pass

class ServiceBase(BaseModel):
    name: str
    description: Optional[str] = None
    duration_minutes: int
    price: float

class ServiceCreate(ServiceBase):
    pass

class Service(ServiceBase):
    id: int
    owner_id: int

    class Config:
        from_attributes = True

class BookingBase(BaseModel):
    customer_name: str
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    start_time: datetime
    end_time: datetime
    service_id: int

    is_recurring: bool = False
    recurrence_pattern: Optional[str] = None
    recurrence_end_date: Optional[date] = None

class BookingCreate(BookingBase):
    pass

class Booking(BookingBase):
    id: int
    owner_id: int
    status: str
    recurrence_group_id: Optional[str] = None

    class Config:
        from_attributes = True

class SubscriptionBase(BaseModel):
    stripe_customer_id: str
    stripe_subscription_id: str
    status: str
    current_period_end: datetime

class SubscriptionCreate(SubscriptionBase):
    owner_id: int

class Subscription(SubscriptionBase):
    id: int
    owner_id: int

    class Config:
        from_attributes = True

class BookingCount(BaseModel):
    month: str
    count: int

class PopularService(BaseModel):
    service_name: str
    booking_count: int

class AdminOwnerUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    locale: Optional[str] = None
    is_active: Optional[bool] = None
    stripe_customer_id: Optional[str] = None

class AdminServiceUpdate(ServiceBase):
    pass

class AdminBookingUpdate(BaseModel):
    customer_name: Optional[str] = None
    customer_email: Optional[EmailStr] = None
    customer_phone: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    status: Optional[str] = None
    service_id: Optional[int] = None
    owner_id: Optional[int] = None
