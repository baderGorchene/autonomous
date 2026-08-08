from pydantic import BaseModel, EmailStr, Field
from typing import List, Optional
from datetime import datetime

class ServiceBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    duration_minutes: int = Field(..., gt=0)
    price: int = Field(..., ge=0) # Price in smallest currency unit (e.g., cents)

class ServiceCreate(ServiceBase):
    pass

class Service(ServiceBase):
    id: int
    owner_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class OwnerBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    phone: Optional[str] = Field(None, pattern=r"^\+?[1-9]\d{1,14}$", description="Phone number in E.164 format (e.g., +1234567890)") # E.164 format
    is_admin: bool = False # Added for admin panel

class OwnerCreate(OwnerBase):
    password: str = Field(..., min_length=8)

class OwnerProfileUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    phone: Optional[str] = Field(None, pattern=r"^\+?[1-9]\d{1,14}$", description="Phone number in E.164 format (e.g., +1234567890)") # E.164 format

class OwnerAdminUpdate(BaseModel): # New schema for admin updates
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, pattern=r"^\+?[1-9]\d{1,14}$", description="Phone number in E.164 format (e.g., +1234567890)")
    subscription_status: Optional[str] = None # free, premium, cancelled
    is_admin: Optional[bool] = None

class Owner(OwnerBase):
    id: int
    created_at: datetime
    updated_at: datetime
    subscription_status: str
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None
    services: List[Service] = []

    class Config:
        from_attributes = True

class BookingBase(BaseModel):
    customer_name: str = Field(..., min_length=1, max_length=100)
    customer_email: EmailStr
    customer_phone: Optional[str] = Field(None, pattern=r"^\+?[1-9]\d{1,14}$", description="Customer phone number in E.164 format (e.g., +1234567890)")
    booking_time: datetime
    service_id: int

class BookingCreate(BookingBase):
    pass

class Booking(BookingBase):
    id: int
    owner_id: int
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None

class OwnerAnalytics(BaseModel):
    total_bookings: int
    monthly_bookings: List[dict]
    popular_services: List[dict]
