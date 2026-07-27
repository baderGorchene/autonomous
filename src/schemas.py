from pydantic import BaseModel, EmailStr, Field
from typing import List, Dict, Any, Optional

class ServiceBase(BaseModel):
    name: str
    description: Optional[str] = None
    duration_minutes: int
    price: float

class ServiceCreate(ServiceBase):
    pass

class Service(ServiceBase):
    id: int # Assuming services might get an ID if stored separately
    class Config:
        from_attributes = True

class AvailabilitySlot(BaseModel):
    day_of_week: str # e.g., "Monday", "Tuesday"
    start_time: str # e.g., "09:00"
    end_time: str # e.g., "17:00"

class OwnerBase(BaseModel):
    name: str
    email: EmailStr
    business_name: str
    slug: str = Field(..., pattern=r"^[a-z0-9-]+$") # enforce slug format
    phone: Optional[str] = None

class OwnerCreate(OwnerBase):
    password: str

class OwnerProfileUpdate(OwnerBase):
    services: List[ServiceCreate] = []
    availability: Dict[str, List[AvailabilitySlot]] = {}

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
    booking_date: str
    booking_time: str

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

class MessageResponse(BaseModel):
    message: str
