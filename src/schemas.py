from pydantic import BaseModel, EmailStr, Field
from datetime import datetime, date, time
from typing import List, Optional

# --- Owner Schemas ---
class OwnerBase(BaseModel):
    email: EmailStr
    name: str
    phone: Optional[str] = None
    profile_picture_url: Optional[str] = None
    booking_page_slug: str
    currency: Optional[str] = "USD"
    locale: Optional[str] = "en"

class OwnerCreate(OwnerBase):
    password: str

class OwnerUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    profile_picture_url: Optional[str] = None
    booking_page_slug: Optional[str] = None
    currency: Optional[str] = None
    locale: Optional[str] = None

class Owner(OwnerBase):
    id: int
    is_active: bool
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None
    subscription_status: str

    class Config:
        from_attributes = True

class OwnerLogin(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None

# --- Service Schemas ---
class ServiceBase(BaseModel):
    name: str
    description: Optional[str] = None
    duration_minutes: int = Field(..., gt=0)
    price: float = Field(..., ge=0) # Should be int for cents
    is_active: Optional[bool] = True

class ServiceCreate(ServiceBase):
    pass

class Service(ServiceBase):
    id: int
    owner_id: int

    class Config:
        from_attributes = True

# --- Availability Schemas (Modified) ---
class AvailabilityBase(BaseModel):
    start_time_of_day: time
    end_time_of_day: time
    rrule_string: Optional[str] = None # iCalendar RRULE format string
    start_date: date
    end_date: Optional[date] = None
    exception_dates: Optional[List[date]] = [] # List of YYYY-MM-DD dates to exclude

class AvailabilityCreate(AvailabilityBase):
    pass

class Availability(AvailabilityBase):
    id: int
    owner_id: int

    class Config:
        from_attributes = True
        json_encoders = {
            date: lambda v: v.isoformat(),
            time: lambda v: v.isoformat(),
        }

# --- Booking Schemas ---
class BookingBase(BaseModel):
    customer_name: str
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    start_time: datetime
    service_id: int

class BookingCreate(BookingBase):
    pass

class Booking(BookingBase):
    id: int
    owner_id: int
    end_time: datetime
    status: str
    service: Service # Nested service schema

    class Config:
        from_attributes = True

class BookingConfirmation(BaseModel):
    message: str
    booking_details: Booking

# --- Analytics Schemas ---
class BookingCount(BaseModel):
    month: str
    count: int

class PopularService(BaseModel):
    service_name: str
    booking_count: int

class DashboardAnalytics(BaseModel):
    total_bookings_this_month: int
    monthly_booking_counts: List[BookingCount]
    popular_services: List[PopularService]
