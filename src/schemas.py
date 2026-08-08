from pydantic import BaseModel, EmailStr, Field
from typing import List, Optional
import datetime

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None

class OwnerBase(BaseModel):
    email: EmailStr
    name: str
    phone: Optional[str] = None
    locale: str = "en"

class OwnerCreate(OwnerBase):
    password: str = Field(..., min_length=8)

class OwnerUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    locale: Optional[str] = None

class OwnerInDB(OwnerBase):
    id: int
    is_active: bool
    stripe_customer_id: Optional[str] = None
    subscription_status: str
    current_period_end: Optional[datetime.datetime] = None

    class Config:
        from_attributes = True

class ServiceBase(BaseModel):
    name: str
    description: str
    duration_minutes: int = Field(..., gt=0)
    price: float = Field(..., ge=0.0)

class ServiceCreate(ServiceBase):
    pass

class ServiceUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    duration_minutes: Optional[int] = None
    price: Optional[float] = None

class Service(ServiceBase):
    id: int
    owner_id: int

    class Config:
        from_attributes = True

class AvailabilityBase(BaseModel):
    date: datetime.date
    start_time: datetime.time
    end_time: datetime.time
    service_id: Optional[int] = None
    is_available: bool = True

class AvailabilityCreate(AvailabilityBase):
    pass

class Availability(AvailabilityBase):
    id: int
    owner_id: int

    class Config:
        from_attributes = True

class RecurringAvailabilityBase(BaseModel):
    service_id: Optional[int] = None
    day_of_week: int = Field(..., ge=0, le=6, description="Day of week (0=Monday, 6=Sunday)")
    start_time: datetime.time
    end_time: datetime.time
    start_date: Optional[datetime.date] = None
    end_date: Optional[datetime.date] = None
    is_active: bool = True

class RecurringAvailabilityCreate(RecurringAvailabilityBase):
    pass

class RecurringAvailabilityUpdate(BaseModel):
    service_id: Optional[int] = None
    day_of_week: Optional[int] = Field(None, ge=0, le=6, description="Day of week (0=Monday, 6=Sunday)")
    start_time: Optional[datetime.time] = None
    end_time: Optional[datetime.time] = None
    start_date: Optional[datetime.date] = None
    end_date: Optional[datetime.date] = None
    is_active: Optional[bool] = None

class RecurringAvailability(RecurringAvailabilityBase):
    id: int
    owner_id: int

    class Config:
        from_attributes = True

class BookingBase(BaseModel):
    customer_name: str
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    booking_time: datetime.datetime

class BookingCreate(BookingBase):
    service_id: int

class Booking(BookingBase):
    id: int
    owner_id: int
    service_id: int
    created_at: datetime.datetime

    class Config:
        from_attributes = True

class BookingConfirmation(BaseModel):
    owner_name: str
    owner_email: EmailStr
    customer_name: str
    customer_email: EmailStr
    service_name: str
    booking_time: datetime.datetime
    owner_phone: Optional[str] = None
    customer_phone: Optional[str] = None
    booking_link: Optional[str] = None

class AdminUserBase(BaseModel):
    email: EmailStr

class AdminUserCreate(AdminUserBase):
    password: str

class AdminUser(AdminUserBase):
    id: int
    is_active: bool

    class Config:
        from_attributes = True

class OwnerDashboardStats(BaseModel):
    total_bookings_this_month: int
    total_revenue_this_month: float
    popular_services: List[dict]
    upcoming_bookings: List[Booking]

class StripeCheckoutSession(BaseModel):
    session_url: str

class SubscriptionStatus(BaseModel):
    status: str
    current_period_end: Optional[datetime.datetime] = None
    is_premium: bool

class BookingTimeSlot(BaseModel):
    start_time: datetime.datetime
    end_time: datetime.datetime
    is_bookable: bool

class DailyAvailability(BaseModel):
    date: datetime.date
    slots: List[BookingTimeSlot]

class OwnerServiceWithAvailability(Service):
    recurring_availabilities: List[RecurringAvailability] = []

class OwnerDashboardData(BaseModel):
    owner: OwnerInDB
    services: List[OwnerServiceWithAvailability]
    upcoming_bookings: List[Booking]
    total_bookings_this_month: int
    total_revenue_this_month: float
    popular_services: List[dict]
    subscription_status: SubscriptionStatus
