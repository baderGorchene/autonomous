from pydantic import BaseModel, EmailStr, Field
from typing import List, Optional
import datetime

class ServiceBase(BaseModel):
    name: str
    duration: int # minutes
    price: float
    description: Optional[str] = None

class ServiceCreate(ServiceBase):
    pass

class Service(ServiceBase):
    id: int

    class Config:
        from_attributes = True

class AvailabilitySlot(BaseModel):
    day_of_week: int # Monday is 0, Sunday is 6
    start_time: str # "HH:MM"
    end_time: str # "HH:MM"

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
    services: Optional[List[ServiceCreate]] = None
    availability: Optional[List[AvailabilitySlot]] = None

class Owner(OwnerBase):
    id: int
    is_active: bool = True
    services_json: str # Store as JSON string
    availability_json: str # Store as JSON string

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
    booking_time: str # "HH:MM"

class BookingCreate(BookingBase):
    pass

class Booking(BookingBase):
    id: int
    owner_id: int
    status: str
    created_at: datetime.datetime

    class Config:
        from_attributes = True

class BookingConfirmation(BaseModel):
    message: str
    booking_id: int

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class UpdateServicesRequest(BaseModel):
    services: List[ServiceCreate]

class UpdateAvailabilityRequest(BaseModel):
    availability: List[AvailabilitySlot]

class ErrorResponse(BaseModel):
    detail: str
