from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from typing import List, Dict, Any, Optional

class OwnerBase(BaseModel):
    name: str
    email: EmailStr
    business_name: str
    slug: str

class OwnerCreate(OwnerBase):
    password: str

class Owner(OwnerBase):
    id: int
    services_json: str
    availability_json: str
    phone: Optional[str] = None

    class Config:
        from_attributes = True

class OwnerProfileUpdate(BaseModel):
    name: str
    business_name: str
    phone: Optional[str] = None
    services_json: str = Field(default="[]", description="JSON string of services")
    availability_json: str = Field(default="{}", description="JSON string of availability")

class BookingBase(BaseModel):
    customer_name: str
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    service_name: str
    booking_time: datetime

class BookingCreate(BookingBase):
    status: str = "pending"

class Booking(BookingBase):
    id: int
    owner_id: int
    status: str

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None
