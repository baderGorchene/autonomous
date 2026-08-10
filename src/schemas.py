from pydantic import BaseModel, EmailStr, Field
from datetime import date, time, datetime
from typing import List, Optional
from .models import RecurrenceType, SubscriptionStatus, BookingStatus

class OwnerBase(BaseModel):
    email: EmailStr
    name: Optional[str] = None
    phone: Optional[str] = None

class OwnerCreate(OwnerBase):
    password: str

class OwnerUpdate(OwnerBase):
    pass

class OwnerResponse(OwnerBase):
    id: int
    subscription_status: SubscriptionStatus
    class Config:
        from_attributes = True

class ServiceBase(BaseModel):
    name: str
    description: Optional[str] = None
    duration_minutes: int = Field(..., gt=0)
    price: float = Field(..., gt=0)
    currency: str = "USD"

class ServiceCreate(ServiceBase):
    pass

class ServiceUpdate(ServiceBase):
    pass

class ServiceResponse(ServiceBase):
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

class AvailabilityCreate(AvailabilityBase):
    pass

class AvailabilityResponse(AvailabilityBase):
    id: int
    owner_id: int
    class Config:
        from_attributes = True

class CustomerBase(BaseModel):
    email: EmailStr
    name: Optional[str] = None
    phone: Optional[str] = None

class CustomerCreate(CustomerBase):
    password: str

class CustomerUpdate(CustomerBase):
    pass

class CustomerResponse(CustomerBase):
    id: int
    class Config:
        from_attributes = True

class BookingBase(BaseModel):
    service_id: int
    customer_name: str
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    date: date
    time: time
    is_recurring_booking: Optional[bool] = False
    parent_booking_id: Optional[int] = None

class BookingCreate(BookingBase):
    pass

class BookingResponse(BookingBase):
    id: int
    owner_id: int
    customer_id: Optional[int] = None
    status: BookingStatus
    created_at: datetime
    class Config:
        from_attributes = True

class AvailableSlot(BaseModel):
    time: time

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None

class ReviewCreate(BaseModel):
    service_id: int
    rating: int = Field(..., ge=1, le=5)
    comment: Optional[str] = None

class ReviewResponse(BaseModel):
    id: int
    service_id: int
    customer_id: int
    rating: int
    comment: Optional[str] = None
    created_at: datetime
    customer_name: Optional[str] = None
    class Config:
        from_attributes = True