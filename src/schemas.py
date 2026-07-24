from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from typing import List, Dict, Optional

class ServiceSchema(BaseModel):
    name: str
    description: Optional[str] = None
    duration: int
    price: Optional[float] = None

class AvailabilitySlotSchema(BaseModel):
    day_of_week: int
    start_time: str
    end_time: str

class OwnerBase(BaseModel):
    email: EmailStr
    name: str
    business_name: str
    slug: str

class OwnerCreate(OwnerBase):
    password: str

class OwnerProfileUpdate(BaseModel):
    name: str
    business_name: str
    phone: Optional[str] = None

class OwnerInDB(OwnerBase):
    id: int
    hashed_password: str
    services_json: List[ServiceSchema] = []
    availability_json: Dict[str, List[AvailabilitySlotSchema]] = {}
    phone: Optional[str] = None

    class Config:
        from_attributes = True

class Owner(OwnerBase):
    id: int
    services: List[ServiceSchema] = Field(default_factory=list, alias="services_json")
    availability: Dict[str, List[AvailabilitySlotSchema]] = Field(default_factory=dict, alias="availability_json")
    phone: Optional[str] = None

    class Config:
        from_attributes = True
        populate_by_name = True

class BookingBase(BaseModel):
    customer_name: str
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    service_name: str
    datetime: datetime
    duration: int

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

class LoginForm(BaseModel):
    email: EmailStr
    password: str