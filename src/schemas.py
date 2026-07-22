from pydantic import BaseModel, EmailStr
from typing import List, Dict, Any, Optional
from datetime import datetime

class OwnerBase(BaseModel):
    email: EmailStr
    name: str
    business_name: str
    slug: str

class OwnerCreate(OwnerBase):
    password: str

class Owner(OwnerBase):
    id: int
    services_json: List[Dict[str, Any]]
    availability_json: Dict[str, Any]
    phone: Optional[str] = None
    created_at: datetime

    class Config:
        orm_mode = True

class OwnerProfileUpdate(BaseModel):
    name: str
    business_name: str
    phone: Optional[str] = None

class BookingBase(BaseModel):
    customer_name: str
    customer_email: EmailStr
    customer_phone: str
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
        orm_mode = True

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None
