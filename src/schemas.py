from pydantic import BaseModel, EmailStr, Field
from typing import List, Dict, Any, Optional
import datetime

# --- Owner Schemas ---
class OwnerBase(BaseModel):
    name: str
    email: EmailStr
    business_name: str
    slug: str = Field(..., regex="^[a-z0-9-]+$") # Slug must be lowercase alphanumeric with hyphens

class OwnerCreate(OwnerBase):
    password: str

class OwnerLogin(BaseModel):
    email: EmailStr
    password: str

class ServiceSchema(BaseModel):
    name: str
    description: Optional[str] = None
    duration_minutes: int
    price: Optional[float] = None

class AvailabilitySchema(BaseModel):
    day_of_week: int # 0-6 for Monday-Sunday
    start_time: str # e.g., "09:00"
    end_time: str # e.g., "17:00"

class OwnerProfileUpdate(BaseModel):
    name: str
    business_name: str
    phone: Optional[str] = None
    services: List[ServiceSchema] = []
    availability: List[AvailabilitySchema] = []

class OwnerInDB(OwnerBase):
    id: int
    hashed_password: str
    services_json: str
    availability_json: str
    phone: Optional[str] = None

    class Config:
        from_attributes = True

class OwnerPublic(OwnerBase):
    id: int
    services: List[ServiceSchema] = []
    availability: List[AvailabilitySchema] = []
    
    class Config:
        from_attributes = True

# --- Booking Schemas ---
class BookingBase(BaseModel):
    customer_name: str
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    service_name: str
    booking_time: datetime.datetime
    duration_minutes: int

class BookingCreate(BookingBase):
    pass

class Booking(BookingBase):
    id: int
    owner_id: int
    is_confirmed: bool
    created_at: datetime.datetime

    class Config:
        from_attributes = True

# --- Token Schemas ---
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None

# --- API Responses ---
class MessageResponse(BaseModel):
    message: str

class ErrorResponse(BaseModel):
    detail: str
