from pydantic import BaseModel, EmailStr, Field
from typing import List, Optional, Dict, Any
import datetime

class Service(BaseModel):
    name: str
    description: Optional[str] = None
    duration_minutes: int
    price: float

class OwnerBase(BaseModel):
    name: str
    email: EmailStr
    business_name: str
    slug: str = Field(pattern=r"^[a-z0-9-]+", description="URL-friendly identifier")
    phone: Optional[str] = None

class OwnerCreate(OwnerBase):
    password: str

class OwnerProfileUpdate(BaseModel):
    name: str
    business_name: str
    phone: Optional[str] = None

class Owner(OwnerBase):
    id: int
    is_active: bool = True
    services_json: str
    availability_json: str

    class Config:
        from_attributes = True

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
    booking_date: datetime.date
    booking_time: str # e.g., "09:00 AM"

class BookingCreate(BookingBase):
    pass

class Booking(BookingBase):
    id: int
    owner_id: int
    status: str
    
    class Config:
        from_attributes = True

class AvailabilitySlot(BaseModel):
    day_of_week: str # e.g., "Monday"
    start_time: str # e.g., "09:00"
    end_time: str # e.g., "17:00"

class OwnerAvailability(BaseModel):
    availability: Dict[str, List[AvailabilitySlot]]
