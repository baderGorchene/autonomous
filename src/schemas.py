from pydantic import BaseModel, EmailStr, Field, validator
from typing import List, Optional, Dict, Any
import json

class ServiceBase(BaseModel):
    name: str
    duration: int = Field(..., gt=0, description="Duration in minutes")
    price: float = Field(..., gt=0, description="Price of the service")

class Service(ServiceBase):
    id: int

    class Config:
        from_attributes = True

class AvailabilitySlot(BaseModel):
    start: str = Field(..., pattern=r"^\d{2}:\d{2}$") # HH:MM
    end: str = Field(..., pattern=r"^\d{2}:\d{2}$")   # HH:MM

class OwnerBase(BaseModel):
    name: str
    email: EmailStr
    business_name: str
    slug: str = Field(..., min_length=3, max_length=50, pattern=r"^[a-z0-9-]+$")
    phone: Optional[str] = None

class OwnerCreate(OwnerBase):
    password: str = Field(..., min_length=8)

class OwnerProfileUpdate(OwnerBase):
    services: List[ServiceBase] = Field(default_factory=list)
    availability: Dict[str, List[AvailabilitySlot]] = Field(default_factory=dict)

    @validator('services', pre=True)
    def parse_services_json(cls, v):
        if isinstance(v, str):
            return json.loads(v)
        return v

    @validator('availability', pre=True)
    def parse_availability_json(cls, v):
        if isinstance(v, str):
            return json.loads(v)
        return v

class Owner(OwnerBase):
    id: int
    is_active: bool
    services_json: str
    availability_json: str

    class Config:
        from_attributes = True

class BookingBase(BaseModel):
    customer_name: str
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    service_name: str
    booking_date: str # YYYY-MM-DD
    booking_time: str # HH:MM

class BookingCreate(BookingBase):
    pass

class Booking(BookingBase):
    id: int
    owner_id: int
    created_at: datetime

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None
