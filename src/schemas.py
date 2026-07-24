from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import List, Dict, Optional, Any

class ServiceSchema(BaseModel):
    name: str
    duration_minutes: int
    price: str

class AvailabilitySchema(BaseModel):
    day: str
    start_time: str
    end_time: str

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
    services_json: List[ServiceSchema] = []
    availability_json: Dict[str, Any] = {}
    phone: Optional[str] = None

    class Config:
        from_attributes = True

class BookingBase(BaseModel):
    service_name: str
    datetime: datetime
    customer_name: str
    customer_email: EmailStr
    customer_phone: Optional[str] = None

class BookingCreate(BookingBase):
    pass

class Booking(BookingBase):
    id: int
    owner_id: int

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    id: Optional[int] = None
