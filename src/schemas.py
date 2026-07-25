from pydantic import BaseModel, EmailStr, Field
from typing import List, Dict, Any, Optional
from datetime import datetime

class Service(BaseModel):
    name: str
    description: Optional[str] = None
    price: Optional[float] = None
    duration_minutes: int

class AvailabilitySlot(BaseModel):
    start_time: str # e.g., "09:00"
    end_time: str   # e.g., "17:00"

class DayAvailability(BaseModel):
    day_of_week: str # e.g., "Monday"
    slots: List[AvailabilitySlot]

class OwnerBase(BaseModel):
    name: str
    email: EmailStr
    business_name: str
    slug: str

class OwnerCreate(OwnerBase):
    password: str

class OwnerProfileUpdate(BaseModel):
    name: str
    business_name: str
    phone: Optional[str] = None

class Owner(OwnerBase):
    id: int
    services_json: List[Service] = []
    availability_json: Dict[str, List[AvailabilitySlot]] = {} # e.g., {"Monday": [{"start_time": "09:00", "end_time": "17:00"}]}
    phone: Optional[str] = None
    
    class Config:
        from_attributes = True

class BookingBase(BaseModel):
    customer_name: str
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    service_name: str
    booking_time: datetime

class BookingCreate(BookingBase):
    pass

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
