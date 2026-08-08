from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field

class ServiceBase(BaseModel):
    name: str
    description: Optional[str] = None
    duration_minutes: int
    price: float

class ServiceCreate(ServiceBase):
    pass

class Service(ServiceBase):
    id: int
    owner_id: int

    class Config:
        from_attributes = True

class AvailabilityBase(BaseModel):
    day_of_week: int # 0-6 for Monday-Sunday
    start_time: str # HH:MM
    end_time: str   # HH:MM

class AvailabilityCreate(AvailabilityBase):
    pass

class Availability(AvailabilityBase):
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
    locale: str = "en" # Added for i18n

class BookingCreate(BookingBase):
    pass

class Booking(BookingBase):
    id: int
    owner_id: int
    service: Service # Nested service schema

    class Config:
        from_attributes = True

class OwnerBase(BaseModel):
    email: EmailStr
    name: Optional[str] = None
    phone: Optional[str] = None

class OwnerCreate(OwnerBase):
    password: str
    subscription_status: Optional[str] = None # 'free' or 'premium'

class OwnerProfileUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None # Allow email update

class OwnerAdminUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    hashed_password: Optional[str] = None # Admin might need to reset password
    subscription_status: Optional[str] = None # 'free', 'premium', 'cancelled'
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None
    is_admin: Optional[bool] = None # Admin can grant admin status

class Owner(OwnerBase):
    id: int
    is_active: bool
    services: List[Service] = []
    availabilities: List[Availability] = []
    bookings: List[Booking] = []
    subscription_status: str
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None
    is_admin: bool = False # Make sure this is present and matches model

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None

class Message(BaseModel):
    message: str

class AnalyticsData(BaseModel):
    total_bookings: int
    monthly_bookings: List[dict]
    popular_services: List[dict]
