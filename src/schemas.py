from pydantic import BaseModel, EmailStr, Field
from typing import List, Optional, Dict, Any
from datetime import datetime

# Service Schema (for JSON storage within Owner)
class ServiceSchema(BaseModel):
    name: str
    duration_minutes: int
    price: float

# Availability Schema (for JSON storage within Owner)
class AvailabilitySchema(BaseModel):
    day_of_week: str # e.g., "Monday", "Tuesday"
    start_time: str # e.g., "09:00"
    end_time: str # e.g., "17:00"

# Owner Schemas
class OwnerBase(BaseModel):
    email: EmailStr
    name: str
    business_name: str
    slug: str # Unique identifier for public booking page URL
    phone: Optional[str] = None # Added for WhatsApp notifications

class OwnerCreate(OwnerBase):
    password: str

class OwnerProfileUpdate(BaseModel):
    name: str
    business_name: str
    phone: Optional[str] = None
    # services_json and availability_json are handled as raw JSON strings in main.py for flexibility

class OwnerInDB(OwnerBase):
    id: int
    services_json: str = "[]"  # Store as JSON string
    availability_json: str = "{}" # Store as JSON string

    class Config:
        from_attributes = True

# Booking Schemas
class BookingBase(BaseModel):
    customer_name: str
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    service_name: str
    booking_time: datetime # Use datetime object

class BookingCreate(BookingBase):
    pass

class BookingInDB(BookingBase):
    id: int
    owner_id: int
    status: str
    created_at: datetime

    class Config:
        from_attributes = True

# Security Schemas
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None
