from pydantic import BaseModel, EmailStr
from datetime import date, time, datetime
from typing import Optional, List

class OwnerBase(BaseModel):
    email: EmailStr
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
    duration_minutes: int
    price: float
    currency: str

class ServiceCreate(ServiceBase):
    pass

class ServiceRead(ServiceBase):
    id: int
    owner_id: int

    class Config:
        from_attributes = True

class OwnerAvailabilityBase(BaseModel):
    day_of_week: Optional[int] = None # 0=Monday, 6=Sunday
    start_time: time
    end_time: time
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    recurrence_type: str = "one_off" # "one_off", "daily", "weekly"

class OwnerAvailabilityCreate(OwnerAvailabilityBase):
    pass

class OwnerAvailabilityRead(OwnerAvailabilityBase):
    id: int
    owner_id: int

    class Config:
        from_attributes = True

class BookingBase(BaseModel):
    service_id: int
    customer_name: str
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    booking_time: datetime
    status: str = "confirmed"

class BookingCreate(BookingBase):
    pass

class BookingRead(BookingBase):
    id: int
    owner_id: int

    class Config:
        from_attributes = True
