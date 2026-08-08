from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from typing import List, Optional, Any, Dict

# Existing schemas (minimal representation for context)
class OwnerBase(BaseModel):
    email: EmailStr
    name: str
    phone: Optional[str] = None

class OwnerCreate(OwnerBase):
    password: str

class OwnerProfileUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None

class OwnerInDB(OwnerBase):
    id: int
    hashed_password: str
    is_active: bool = True
    is_premium: bool = False

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None

class ServiceBase(BaseModel):
    name: str
    duration_minutes: int
    price: float
    description: Optional[str] = None

class ServiceCreate(ServiceBase):
    pass

class ServiceUpdate(ServiceBase):
    name: Optional[str] = None
    duration_minutes: Optional[int] = None
    price: Optional[float] = None
    description: Optional[str] = None

class Service(ServiceBase):
    id: int
    owner_id: int

    class Config:
        from_attributes = True

class BookingBase(BaseModel):
    service_id: int
    customer_name: str
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    start_time: datetime
    end_time: datetime
    status: str = "pending"

class BookingCreate(BookingBase):
    pass

class BookingResponse(BookingBase):
    id: int
    owner_id: int

    class Config:
        from_attributes = True

class BookingDisplay(BaseModel):
    id: int
    service_name: str
    customer_name: str
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    start_time: datetime
    end_time: datetime
    status: str
    price: float

    class Config:
        from_attributes = True

# New schema for analytics
class AnalyticsResponse(BaseModel):
    total_bookings: int
    upcoming_bookings: int
    completed_bookings: int
