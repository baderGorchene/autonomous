from pydantic import BaseModel, EmailStr, Field, validator
from datetime import datetime, date, time
from typing import List, Optional, Dict

class OwnerBase(BaseModel):
    email: EmailStr
    name: str
    phone: Optional[str] = None

class OwnerCreate(OwnerBase):
    password: str

class OwnerProfileUpdate(OwnerBase):
    email: Optional[EmailStr] = None
    name: Optional[str] = None
    phone: Optional[str] = None

class Owner(OwnerBase):
    id: int
    is_active: bool
    is_premium: bool
    created_at: datetime

    class Config:
        from_attributes = True

class ServiceBase(BaseModel):
    name: str
    description: Optional[str] = None
    price: float
    duration_minutes: int

class ServiceCreate(ServiceBase):
    pass

class Service(ServiceBase):
    id: int
    owner_id: int

    class Config:
        from_attributes = True

class BookingBase(BaseModel):
    customer_name: str
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    service_id: int
    booking_time: datetime

class BookingCreate(BookingBase):
    pass

class Booking(BookingBase):
    id: int
    owner_id: int
    service: Service

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None

class MonthlyBookingCount(BaseModel):
    month: str
    count: int

class PopularService(BaseModel):
    service_name: str
    count: int

class OwnerAnalytics(BaseModel):
    total_bookings: int
    monthly_bookings: List[MonthlyBookingCount]
    popular_services: List[PopularService]
