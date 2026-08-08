from pydantic import BaseModel, EmailStr, Field
from datetime import datetime, timedelta
from typing import Optional, List

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None

class OwnerBase(BaseModel):
    email: EmailStr
    name: str
    phone: Optional[str] = None
    language: Optional[str] = "en"

class OwnerCreate(OwnerBase):
    password: str

class OwnerInDB(OwnerBase):
    id: int
    is_active: bool
    
    class Config:
        from_attributes = True

class ServiceBase(BaseModel):
    name: str
    description: Optional[str] = None
    duration_minutes: int = Field(..., gt=0)
    price: float = Field(..., ge=0)

class ServiceCreate(ServiceBase):
    pass

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

class BookingCreate(BookingBase):
    is_recurring: bool = False
    recurrence_pattern: Optional[str] = None
    recurrence_end_date: Optional[datetime] = None
    recurrence_end_count: Optional[int] = None

class Booking(BookingBase):
    id: int
    owner_id: int
    end_time: datetime
    status: str
    
    is_recurring: bool
    recurrence_pattern: Optional[str] = None
    recurrence_end_date: Optional[datetime] = None
    recurrence_end_count: Optional[int] = None
    parent_booking_id: Optional[int] = None

    class Config:
        from_attributes = True

class SubscriptionBase(BaseModel):
    stripe_customer_id: str
    stripe_subscription_id: str
    status: str
    current_period_end: datetime

class SubscriptionCreate(SubscriptionBase):
    owner_id: int

class Subscription(SubscriptionBase):
    id: int
    owner_id: int

    class Config:
        from_attributes = True

class AdminUser(BaseModel):
    email: EmailStr
    is_admin: bool = True

class AdminUserCreate(AdminUser):
    password: str

class AdminUserInDB(AdminUser):
    id: int
    hashed_password: str

    class Config:
        from_attributes = True

class AnalyticsData(BaseModel):
    total_bookings_this_month: int
    popular_services: List[dict]

class UpcomingBooking(Booking):
    service_name: str
    service_duration: int
    service_price: float
