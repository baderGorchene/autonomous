from pydantic import BaseModel, EmailStr, Field
from typing import List, Dict, Any, Optional
from datetime import date, datetime

class ServiceBase(BaseModel):
    name: str
    duration_minutes: int
    price: float

class ServiceCreate(ServiceBase):
    pass

class AvailabilitySlot(BaseModel):
    day: str # e.g., "Monday"
    start_time: str # e.g., "09:00"
    end_time: str # e.g., "17:00"

class OwnerBase(BaseModel):
    name: str
    email: EmailStr
    business_name: str
    slug: str
    phone: Optional[str] = None

class OwnerCreate(OwnerBase):
    password: str

class OwnerProfileUpdate(BaseModel):
    name: str
    business_name: str
    phone: Optional[str] = None
    services: List[ServiceCreate] = Field(default_factory=list)
    availability: Dict[str, List[AvailabilitySlot]] = Field(default_factory=dict) # e.g., {"Monday": [{"start_time": "09:00", "end_time": "17:00"}]}

class Owner(OwnerBase):
    id: int
    services_json: str
    availability_json: str

    class Config:
        from_attributes = True

class BookingBase(BaseModel):
    customer_name: str
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    service_name: str
    booking_date: date
    booking_time: str # e.g., "10:00 AM"

class BookingCreate(BookingBase):
    pass

class Booking(BookingBase):
    id: int
    owner_id: int
    status: str
    booking_date: datetime # Override to datetime for consistency with DB model

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None

class MessageResponse(BaseModel):
    message: str

class ErrorResponse(BaseModel):
    detail: str
