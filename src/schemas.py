from pydantic import BaseModel, EmailStr, Field
from typing import List, Dict, Any, Optional
import datetime

# --- Owner Schemas ---
class OwnerBase(BaseModel):
    name: str
    email: EmailStr
    business_name: str
    slug: str = Field(..., pattern=r"^[a-z0-9-]+$", min_length=3, max_length=50)
    phone: Optional[str] = None

class OwnerCreate(OwnerBase):
    password: str

class OwnerProfileUpdate(BaseModel):
    name: str
    business_name: str
    phone: Optional[str] = None
    services: List[Dict[str, Any]] = Field(default_factory=list)
    availability: Dict[str, Any] = Field(default_factory=dict)

class OwnerInDB(OwnerBase):
    id: int
    hashed_password: str
    is_active: bool
    services_json: str
    availability_json: str

    class Config:
        from_attributes = True

class OwnerResponse(OwnerBase):
    id: int
    services: List[Dict[str, Any]]
    availability: Dict[str, Any]

    class Config:
        from_attributes = True

# --- Booking Schemas ---
class BookingBase(BaseModel):
    customer_name: str
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    service_name: str
    booking_date: datetime.date
    booking_time: str # e.g., "09:00", "10:30"

class BookingCreate(BookingBase):
    pass

class Booking(BookingBase):
    id: int
    owner_id: int
    created_at: datetime.datetime

    class Config:
        from_attributes = True

# --- Auth Schemas ---
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None

class LoginForm(BaseModel):
    username: str
    password: str
