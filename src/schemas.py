from pydantic import BaseModel, EmailStr, Field
from datetime import datetime, date, time
from typing import Optional, List

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None

class OwnerBase(BaseModel):
    email: EmailStr
    company_name: Optional[str] = None
    phone: Optional[str] = None

class OwnerCreate(OwnerBase):
    password: str

class Owner(OwnerBase):
    id: int
    is_active: bool

    class Config:
        from_attributes = True

class AvailabilityBase(BaseModel):
    start_time: time
    end_time: time
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    is_recurring: bool = False
    recurrence_type: Optional[str] = None
    recurrence_details: Optional[str] = None

class AvailabilityCreate(AvailabilityBase):
    pass

class Availability(AvailabilityBase):
    id: int
    owner_id: int
    service_id: Optional[int] = None

    class Config:
        from_attributes = True

class ServiceBase(BaseModel):
    name: str = Field(..., min_length=1)
    description: Optional[str] = None
    duration_minutes: int = Field(30, ge=5, le=480)
    price: float = Field(0.0, ge=0.0)

class ServiceCreate(ServiceBase):
    pass

class Service(ServiceBase):
    id: int
    owner_id: int
    availabilities: List[Availability] = []
    
    class Config:
        from_attributes = True

class BookingBase(BaseModel):
    service_id: int
    customer_name: str
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    start_time: datetime

class BookingCreate(BookingBase):
    pass

class Booking(BookingBase):
    id: int
    owner_id: int
    end_time: datetime
    status: str

    class Config:
        from_attributes = True

class OwnerUpdate(BaseModel):
    email: Optional[EmailStr] = None
    company_name: Optional[str] = None
    phone: Optional[str] = None
    password: Optional[str] = None

class AnalyticsData(BaseModel):
    total_bookings_month: int
    popular_services: List[dict]

class StripeCheckoutSession(BaseModel):
    url: str

class AdminOwnerUpdate(BaseModel):
    email: Optional[EmailStr] = None
    is_active: Optional[bool] = None
    company_name: Optional[str] = None
    phone: Optional[str] = None

class AdminServiceUpdate(ServiceBase):
    pass

class AdminBookingUpdate(BaseModel):
    customer_name: Optional[str] = None
    customer_email: Optional[EmailStr] = None
    customer_phone: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    status: Optional[str] = None
