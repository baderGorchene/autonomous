from pydantic import BaseModel, EmailStr, Field
from typing import List, Optional
from datetime import date, time

class ServiceSchema(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    price: float = Field(..., gt=0)
    duration_minutes: int = Field(..., gt=0, description="Duration of the service in minutes")

class OwnerBase(BaseModel):
    email: EmailStr
    name: str = Field(..., min_length=1, max_length=100)
    business_name: str = Field(..., min_length=1, max_length=100)
    phone: Optional[str] = Field(None, pattern=r"^\+?[1-9]\d{1,14}$", description="E.164 format phone number") # Basic E.164 validation

class OwnerCreate(OwnerBase):
    password: str = Field(..., min_length=8)
    slug: str = Field(..., min_length=3, max_length=50, pattern=r"^[a-z0-9-]+$") # Lowercase, numbers, hyphens

class OwnerLogin(BaseModel):
    email: EmailStr
    password: str

class Owner(OwnerBase):
    id: int
    slug: str
    services_json: str # JSON string of List[ServiceSchema]
    availability_json: str # JSON string of Dict[str, List[str]]
    is_active: bool = True

    class Config:
        from_attributes = True

class OwnerProfileUpdate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    business_name: str = Field(..., min_length=1, max_length=100)
    phone: Optional[str] = Field(None, pattern=r"^\+?[1-9]\d{1,14}$")
    services_json: Optional[str] = Field(None, description="JSON string representing a list of ServiceSchema objects") # Keep as string for Form data
    availability_json: Optional[str] = Field(None, description="JSON string representing availability slots")

class BookingBase(BaseModel):
    customer_name: str = Field(..., min_length=1, max_length=100)
    customer_email: EmailStr
    customer_phone: Optional[str] = Field(None, pattern=r"^\+?[1-9]\d{1,14}$")
    service_name: str = Field(..., min_length=1, max_length=100)
    booking_date: date
    booking_time: time

class BookingCreate(BookingBase):
    pass

class Booking(BookingBase):
    id: int
    owner_id: int
    service_duration_minutes: int # Added to the output schema for consistency
    
    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None
