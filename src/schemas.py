from pydantic import BaseModel, EmailStr, Field
from datetime import date, time, datetime
from typing import Optional, List
import enum

class RecurrenceType(str, enum.Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"

class OwnerBase(BaseModel):
    name: str
    email: EmailStr
    phone: Optional[str] = None

class OwnerCreate(OwnerBase):
    password: str

class OwnerUpdate(OwnerBase):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None

class OwnerInDBBase(OwnerBase):
    id: int
    is_active: bool
    created_at: datetime
    subscription_status: str
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None

    class Config:
        from_attributes = True

class OwnerDisplay(OwnerInDBBase):
    pass

class ServiceBase(BaseModel):
    name: str
    description: Optional[str] = None
    duration_minutes: int = Field(..., gt=0)
    price: float = Field(..., ge=0)
    is_active: Optional[bool] = True

class ServiceCreate(ServiceBase):
    pass

class ServiceUpdate(ServiceBase):
    name: Optional[str] = None
    description: Optional[str] = None
    duration_minutes: Optional[int] = None
    price: Optional[float] = None
    is_active: Optional[bool] = None

class ServiceInDBBase(ServiceBase):
    id: int
    owner_id: int
    created_at: datetime

    class Config:
        from_attributes = True

class ServiceDisplay(ServiceInDBBase):
    pass

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
    service_id: Optional[int] = None
    date: Optional[date] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    recurrence_type: Optional[RecurrenceType] = None
    recurrence_value: Optional[str] = None
    recurrence_start_date: Optional[date] = None
    recurrence_end_date: Optional[date] = None

class AvailabilityInDBBase(AvailabilityBase):
    id: int
    owner_id: int
    created_at: datetime

    class Config:
        from_attributes = True

class AvailabilityDisplay(AvailabilityInDBBase):
    pass

# Customer Schemas
class CustomerBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    email: Optional[EmailStr] = None
    phone: Optional[str] = None

class CustomerCreate(CustomerBase):
    password: Optional[str] = None # Optional for registration, if customer chooses to create an account
    owner_id: int # To link customer to an owner's booking page

class CustomerUpdate(CustomerBase):
    pass

class CustomerInDBBase(CustomerBase):
    id: int
    owner_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class CustomerDisplay(CustomerInDBBase):
    pass

# Update Booking Schemas
class BookingBase(BaseModel):
    service_id: int
    customer_name: str
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    date: date
    time: time
    is_recurring: Optional[bool] = False
    recurrence_id: Optional[str] = None
    customer_id: Optional[int] = None # New: Optional customer ID

class BookingCreate(BookingBase):
    pass

class BookingUpdate(BookingBase):
    is_confirmed: Optional[bool] = None

class BookingInDBBase(BookingBase):
    id: int
    owner_id: int
    is_confirmed: bool
    created_at: datetime

    class Config:
        from_attributes = True

class BookingDisplay(BookingInDBBase):
    service: Optional[ServiceDisplay] = None
    customer: Optional[CustomerDisplay] = None # New: Optional customer details
