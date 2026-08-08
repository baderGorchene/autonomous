from pydantic import BaseModel, EmailStr, Field
from typing import List, Optional
from datetime import datetime, date

# Owner Schemas
class OwnerBase(BaseModel):
    email: EmailStr
    name: str
    phone: Optional[str] = None

class OwnerCreate(OwnerBase):
    password: str
    subscription_status: str = "free"

class OwnerProfileUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None

class Owner(OwnerBase):
    id: int
    subscription_status: str
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None

    class Config:
        from_attributes = True

# Service Schemas
class ServiceBase(BaseModel):
    name: str
    description: Optional[str] = None
    duration: int # in minutes
    price: float = Field(..., ge=0) # price for the service

class ServiceCreate(ServiceBase):
    pass

class Service(ServiceBase):
    id: int
    owner_id: int

    class Config:
        from_attributes = True

# Booking Schemas
class BookingBase(BaseModel):
    customer_name: str
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    booking_time: datetime
    service_id: int

class BookingCreate(BookingBase):
    pass

class Booking(BookingBase):
    id: int
    owner_id: int
    created_at: datetime

    class Config:
        from_attributes = True

# Security Schemas
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None

# Analytics Schemas
class MonthlyBooking(BaseModel):
    month: str
    count: int

class PopularService(BaseModel):
    service_name: str
    count: int

class OwnerAnalytics(BaseModel):
    total_bookings: int
    monthly_bookings: List[MonthlyBooking]
    popular_services: List[PopularService]
