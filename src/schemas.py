from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from typing import List, Optional

class OwnerBase(BaseModel):
    email: EmailStr
    name: str
    phone: Optional[str] = None

class OwnerCreate(OwnerBase):
    password: str

class Owner(OwnerBase):
    id: int
    is_active: bool = True

    class Config:
        from_attributes = True

class OwnerProfileUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None

class ServiceBase(BaseModel):
    name: str
    description: Optional[str] = None
    duration_minutes: int
    price: int

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
    booking_time: datetime
    service_id: int

class BookingCreate(BookingBase):
    pass

class Booking(BookingBase):
    id: int
    owner_id: int
    
    service: Service

    class Config:
        from_attributes = True

class MonthlyBookingData(BaseModel):
    month: str
    count: int

class PopularServiceData(BaseModel):
    service_name: str
    count: int

class OwnerAnalytics(BaseModel):
    total_bookings: int
    monthly_bookings: List[MonthlyBookingData]
    popular_services: List[PopularServiceData]
