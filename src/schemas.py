from pydantic import BaseModel, EmailStr
from typing import List, Optional
from datetime import date, time, datetime
from enum import Enum

class RecurrenceTypeEnum(str, Enum):
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"

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
    is_admin: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserProfileUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None

class ServiceBase(BaseModel):
    name: str
    description: Optional[str] = None
    duration_minutes: int
    price: int # Store in cents/smallest unit

class ServiceCreate(ServiceBase):
    pass

class Service(ServiceBase):
    id: int
    owner_id: int
    is_active: bool

    class Config:
        orm_mode = True

class AvailabilityBase(BaseModel):
    service_id: Optional[int] = None
    date: Optional[date] = None
    start_time: time
    end_time: time
    is_active: bool = True
    recurrence_type: Optional[RecurrenceTypeEnum] = None
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

class BookingBase(BaseModel):
    service_id: int
    customer_name: str
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    date: date
    time: time
    is_recurring: bool = False
    recurrence_type: Optional[RecurrenceTypeEnum] = None
    recurrence_value: Optional[str] = None
    recurrence_end_date: Optional[date] = None

class BookingCreate(BookingBase):
    pass

class Booking(BookingBase):
    id: int
    owner_id: int
    status: str
    created_at: datetime
    service: Service # Nested service object
    parent_booking_id: Optional[int] = None

    class Config:
        orm_mode = True

class SubscriptionBase(BaseModel):
    stripe_customer_id: str
    stripe_subscription_id: str
    current_plan_id: str
    status: str
    start_date: datetime
    end_date: Optional[datetime] = None

class SubscriptionCreate(SubscriptionBase):
    owner_id: int

class Subscription(SubscriptionBase):
    id: int
    owner_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True
