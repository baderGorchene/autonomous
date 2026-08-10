from pydantic import BaseModel, EmailStr, Field
from typing import List, Optional, Dict, Any
from datetime import date, time, datetime
from enum import Enum

class OwnerBase(BaseModel):
    email: EmailStr
    name: Optional[str] = None
    phone: Optional[str] = None
    locale: Optional[str] = "en"

class OwnerCreate(OwnerBase):
    password: str

class OwnerUpdate(OwnerBase):
    email: Optional[EmailStr] = None
    name: Optional[str] = None
    phone: Optional[str] = None
    locale: Optional[str] = None

class OwnerInDB(OwnerBase):
    id: int
    is_active: bool
    stripe_customer_id: Optional[str] = None
    subscription_status: str
    subscription_ends_at: Optional[datetime] = None

    class Config:
        orm_mode = True

class Owner(OwnerInDB):
    pass

class ServiceBase(BaseModel):
    name: str
    description: Optional[str] = None
    duration_minutes: int = Field(..., ge=1)
    price: Optional[float] = Field(None, ge=0)

class ServiceCreate(ServiceBase):
    pass

class ServiceUpdate(ServiceBase):
    name: Optional[str] = None
    duration_minutes: Optional[int] = Field(None, ge=1)
    price: Optional[float] = Field(None, ge=0)

class ServiceInDB(ServiceBase):
    id: int
    owner_id: int

    class Config:
        orm_mode = True

class Service(ServiceInDB):
    pass

class RecurrenceType(str, Enum):
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"

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

class AvailabilityUpdate(AvailabilityBase):
    start_time: Optional[time] = None
    end_time: Optional[time] = None

class AvailabilityInDB(AvailabilityBase):
    id: int
    owner_id: int

    class Config:
        orm_mode = True

class Availability(AvailabilityInDB):
    pass

class CustomerBase(BaseModel):
    name: str
    email: EmailStr
    phone: Optional[str] = None

class CustomerCreate(CustomerBase):
    pass

class CustomerUpdate(CustomerBase):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None

class CustomerInDB(CustomerBase):
    id: int
    owner_id: int

    class Config:
        orm_mode = True

class Customer(CustomerInDB):
    pass

class BookingBase(BaseModel):
    service_id: int
    customer_name: str
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    date: date
    time: time
    
    is_recurring: Optional[bool] = False
    recurrence_pattern: Optional[str] = None

class BookingCreate(BookingBase):
    customer_id: Optional[int] = None
    save_customer_details: Optional[bool] = False

class BookingUpdate(BaseModel):
    is_confirmed: Optional[bool] = None

class BookingInDB(BookingBase):
    id: int
    owner_id: int
    created_at: datetime
    is_confirmed: bool
    recurrence_id: Optional[str] = None
    customer_id: Optional[int] = None

    class Config:
        orm_mode = True

class Booking(BookingInDB):
    service: ServiceInDB
    customer: Optional[CustomerInDB] = None

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None

class MonthlyBookingData(BaseModel):
    month: str
    count: int

class PopularServiceData(BaseModel):
    service_name: str
    booking_count: int

class AdminOwnerUpdate(OwnerUpdate):
    is_active: Optional[bool] = None
    subscription_status: Optional[str] = None
    subscription_ends_at: Optional[datetime] = None
    stripe_customer_id: Optional[str] = None

class AdminServiceUpdate(ServiceUpdate):
    owner_id: Optional[int] = None

class AdminBookingUpdate(BookingUpdate):
    owner_id: Optional[int] = None
    service_id: Optional[int] = None
    customer_name: Optional[str] = None
    customer_email: Optional[EmailStr] = None
    customer_phone: Optional[str] = None
    date: Optional[date] = None
    time: Optional[time] = None
    is_recurring: Optional[bool] = None
    recurrence_pattern: Optional[str] = None
    recurrence_id: Optional[str] = None
    customer_id: Optional[int] = None
