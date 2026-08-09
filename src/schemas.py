from pydantic import BaseModel, EmailStr
from datetime import date, time, datetime
from typing import List, Optional, Dict

import enum

class RecurrenceType(str, enum.Enum):
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None

class ServiceBase(BaseModel):
    name: str
    description: Optional[str] = None
    duration_minutes: int
    price: int

class ServiceCreate(ServiceBase):
    pass

class Service(ServiceBase):
    id: int
    owner_id: int
    availabilities: List["Availability"] = []
    bookings: List["Booking"] = []

    class Config:
        orm_mode = True

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

class CustomerBase(BaseModel):
    name: str
    email: EmailStr
    phone_number: Optional[str] = None

class CustomerCreate(CustomerBase):
    owner_id: int

class Customer(CustomerBase):
    id: int
    owner_id: int
    bookings: List["Booking"] = []

    class Config:
        orm_mode = True

class BookingBase(BaseModel):
    service_id: int
    date: date
    time: time
    customer_name: str
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    is_recurring: Optional[bool] = False
    recurrence_id: Optional[str] = None
    customer_id: Optional[int] = None

class BookingCreate(BookingBase):
    pass

class Booking(BookingBase):
    id: int
    owner_id: int
    is_confirmed: bool
    created_at: datetime
    service: "Service"
    customer: Optional[Customer]

    class Config:
        orm_mode = True

class OwnerBase(BaseModel):
    username: str
    email: EmailStr
    phone_number: Optional[str] = None
    currency: Optional[str] = "USD"
    locale: Optional[str] = "en"

class OwnerCreate(OwnerBase):
    password: str

class OwnerUpdate(BaseModel):
    email: Optional[EmailStr] = None
    phone_number: Optional[str] = None
    currency: Optional[str] = None
    locale: Optional[str] = None

class Owner(OwnerBase):
    id: int
    is_active: bool
    created_at: datetime
    services: List[Service] = []
    availabilities: List[Availability] = []
    bookings: List[Booking] = []
    customers: List[Customer] = []
    stripe_customer_id: Optional[str]
    stripe_subscription_id: Optional[str]
    subscription_status: str

    class Config:
        orm_mode = True

class OwnerLogin(BaseModel):
    username: str
    password: str

class SubscriptionUpdate(BaseModel):
    subscription_status: str

class StripeCheckoutSessionResponse(BaseModel):
    session_id: str

# Update forward references
Service.update_forward_refs()
Availability.update_forward_refs()
Customer.update_forward_refs()
Booking.update_forward_refs()
Owner.update_forward_refs()
