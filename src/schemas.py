import uuid
from datetime import datetime, date
from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field
from enum import Enum

class RecurrencePattern(str, Enum):
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"

class OwnerBase(BaseModel):
    email: EmailStr
    name: str
    phone: Optional[str] = None

class OwnerCreate(OwnerBase):
    password: str

class Owner(OwnerBase):
    id: uuid.UUID
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True

class ServiceBase(BaseModel):
    name: str
    description: Optional[str] = None
    duration_minutes: int = Field(..., gt=0)
    price: int = Field(..., ge=0) # Price in smallest currency unit

class ServiceCreate(ServiceBase):
    pass

class Service(ServiceBase):
    id: uuid.UUID
    owner_id: uuid.UUID
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True

class BookingBase(BaseModel):
    service_id: uuid.UUID
    customer_name: str
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    booking_date: date
    booking_time: str # e.g., "10:00"

class BookingCreate(BookingBase):
    is_recurring: bool = False
    recurrence_pattern: Optional[RecurrencePattern] = None
    recurrence_interval: Optional[int] = Field(None, ge=1)
    recurrence_end_date: Optional[date] = None

class Booking(BookingBase):
    id: uuid.UUID
    owner_id: uuid.UUID
    status: str
    created_at: datetime
    is_recurring: bool
    recurrence_pattern: Optional[RecurrencePattern] = None
    recurrence_interval: Optional[int] = None
    recurrence_end_date: Optional[date] = None
    recurring_original_id: Optional[uuid.UUID] = None # UUID type for consistency

    class Config:
        from_attributes = True

# JWT related schemas (assuming these exist)
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None
