from pydantic import BaseModel, EmailStr
from typing import List, Dict, Optional
from datetime import datetime

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None

class OwnerBase(BaseModel):
    name: str
    email: EmailStr
    business_name: str
    slug: str
    phone: Optional[str] = None

class OwnerCreate(OwnerBase):
    password: str

class Owner(OwnerBase):
    id: int
    services_json: List[Dict]
    availability_json: Dict
    created_at: datetime

    class Config:
        from_attributes = True

class OwnerProfileUpdate(BaseModel):
    name: str
    business_name: str
    phone: Optional[str] = None

class BookingBase(BaseModel):
    customer_name: str
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    service: str
    datetime: datetime

class BookingCreate(BookingBase):
    pass

class Booking(BookingBase):
    id: int
    owner_id: int
    status: str
    created_at: datetime

    class Config:
        from_attributes = True
