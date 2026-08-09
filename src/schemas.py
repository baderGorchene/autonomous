from pydantic import BaseModel, EmailStr, Field
from datetime import date, time
from typing import List, Optional
import enum
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
    locale: Optional[str] = "en"

class OwnerCreate(OwnerBase):
    password: str

class OwnerUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    locale: Optional[str] = None
    is_premium: Optional[bool] = None
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None

class OwnerInDB(OwnerBase):
    id: int
    is_premium: bool
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None

    class Config:
        orm_mode = True

class ServiceBase(BaseModel):
    name: str
    description: Optional[str] = None
    duration_minutes: int = Field(..., gt=0)
    price: float = Field(..., gt=0)
    currency: str = "USD"

class ServiceCreate(ServiceBase):
    pass

class ServiceUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    duration_minutes: Optional[int] = Field(None, gt=0)
    price: Optional[float] = Field(None, gt=0)
    currency: Optional[str] = None

class ServiceInDB(ServiceBase):
    id: int
    owner_id: int

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

class AvailabilityUpdate(AvailabilityBase):
    pass

class AvailabilityInDB(AvailabilityBase):
    id: int
    owner_id: int

    class Config:
        orm_mode = True

class CustomerBase(BaseModel):
    name: str
    email: EmailStr
    phone: Optional[str] = None

class CustomerCreate(CustomerBase):
    password: Optional[str] = None

class CustomerLogin(BaseModel):
    email: EmailStr
    password: str

class CustomerInDB(CustomerBase):
    id: int
    owner_id: int
    hashed_password: Optional[str] = None

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

class BookingCreate(BookingBase):
    customer_id: Optional[int] = None

class BookingInDB(BookingBase):
    id: int
    owner_id: int
    customer_id: Optional[int] = None

    class Config:
        orm_mode = True

class BookingWithCustomer(BookingInDB):
    customer: Optional[CustomerInDB] = None
    service: Optional[ServiceInDB] = None

    class Config:
        orm_mode = True

class BookingDate(BaseModel):
    date: date