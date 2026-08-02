from pydantic import BaseModel, EmailStr, Field
from typing import List, Dict, Any, Optional
from datetime import date, time

class ServiceBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    duration_minutes: int = Field(..., gt=0)
    price: Optional[float] = Field(None, ge=0)

class ServiceCreate(ServiceBase):
    pass

class Service(ServiceBase):
    id: int

    class Config:
        from_attributes = True

class AvailabilitySlot(BaseModel):
    day_of_week: str # e.g., "Monday"
    start_time: str # e.g., "09:00"
    end_time: str # e.g., "17:00"

class OwnerBase(BaseModel):
    email: EmailStr
    name: str = Field(..., min_length=1, max_length=100)
    business_name: str = Field(..., min_length=1, max_length=100)
    slug: str = Field(..., min_length=3, max_length=50, regex="^[a-z0-9-]+$") # URL-friendly slug
    phone: Optional[str] = None

class OwnerCreate(OwnerBase):
    password: str = Field(..., min_length=6)

class OwnerProfileUpdate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    business_name: str = Field(..., min_length=1, max_length=100)
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

class Login(BaseModel):
    email: EmailStr
    password: str

class BookingCreate(BaseModel):
    customer_name: str = Field(..., min_length=1, max_length=100)
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    service_name: str = Field(..., min_length=1, max_length=100)
    booking_date: date
    booking_time: time

class Booking(BookingCreate):
    id: int
    owner_id: int
    status: str

    class Config:
        from_attributes = True
        json_encoders = {
            date: lambda v: v.isoformat(),
            time: lambda v: v.isoformat(timespec='minutes')
        }

class AvailabilityUpdate(BaseModel):
    availability: Dict[str, List[AvailabilitySlot]]

class ServicesUpdate(BaseModel):
    services: List[ServiceCreate]


class OwnerDashboardData(BaseModel):
    owner: Owner
    bookings: List[Booking]
    services: List[Service]
    availability: Dict[str, List[AvailabilitySlot]]
