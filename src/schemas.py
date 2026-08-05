from pydantic import BaseModel, EmailStr, Field
from typing import List, Dict, Any, Optional
from datetime import datetime

class OwnerBase(BaseModel):
    name: str
    email: EmailStr
    business_name: str
    slug: str = Field(..., regex="^[a-z0-9-]+$", min_length=3) # Slug for URL
    phone: Optional[str] = None

class OwnerCreate(OwnerBase):
    password: str

class OwnerProfileUpdate(BaseModel):
    name: str
    business_name: str
    phone: Optional[str] = None
    # No email or slug update for simplicity here, would require more complex logic

class OwnerInDB(OwnerBase):
    id: int
    hashed_password: str
    services_json: str
    availability_json: str

    class Config:
        from_attributes = True

class Service(BaseModel):
    name: str
    duration: int # in minutes
    price: float
    currency: str = "USD" # Default currency

class Availability(BaseModel):
    day_of_week: int # 0-6 for Monday-Sunday
    start_time: str # HH:MM
    end_time: str # HH:MM

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None

class BookingBase(BaseModel):
    customer_name: str
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    service_name: str
    booking_date: str # YYYY-MM-DD
    booking_time: str # HH:MM

class BookingCreate(BookingBase):
    pass

class Booking(BookingBase):
    id: int
    owner_id: int
    created_at: datetime

    class Config:
        from_attributes = True

class ErrorResponse(BaseModel):
    detail: str
