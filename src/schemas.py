from pydantic import BaseModel, EmailStr
from datetime import date, time, datetime
from typing import Optional, List
from .models import RecurrenceType # Import the Enum

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None

class OwnerBase(BaseModel):
    email: EmailStr
    name: str
    phone_number: Optional[str] = None
    locale: str = "en"

class OwnerCreate(OwnerBase):
    password: str

class Owner(OwnerBase):
    id: int
    is_premium: bool

    class Config:
        orm_mode = True

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
        orm_mode = True

class AvailabilityBase(BaseModel):
    service_id: Optional[int] = None
    date: Optional[date] = None
    start_time: time
    end_time: time
    recurrence_type: RecurrenceType = RecurrenceType.NONE
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

# New Customer Schemas
class CustomerBase(BaseModel):
    name: str
    email: Optional[EmailStr] = None
    phone_number: Optional[str] = None

class CustomerCreate(CustomerBase):
    pass

class Customer(CustomerBase):
    id: int
    owner_id: int

    class Config:
        orm_mode = True

class BookingBase(BaseModel):
    service_id: int
    date: date
    time: time

class BookingCreate(BookingBase):
    customer_name: str
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    is_recurring: bool = False
    recurrence_end_date: Optional[date] = None

class Booking(BookingBase):
    id: int
    owner_id: int
    customer_id: Optional[int] = None
    is_confirmed: bool
    recurrence_id: Optional[str] = None
    
    customer: Optional[Customer] = None
    service: Optional[Service] = None

    class Config:
        orm_mode = True

# For analytics
class MonthlyBookingsData(BaseModel):
    month: str
    count: int

class PopularServicesData(BaseModel):
    service_name: str
    booking_count: int

class AnalyticsData(BaseModel):
    monthly_bookings: List[MonthlyBookingsData]
    popular_services: List[PopularServicesData]

# For subscription management
class SubscriptionStatus(BaseModel):
    is_premium: bool
    current_plan: str = "Free"
    next_billing_date: Optional[date] = None
    subscription_active: bool = False
