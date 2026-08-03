from pydantic import BaseModel, EmailStr, Field
from typing import List, Dict, Any, Optional
from datetime import datetime

class ServiceBase(BaseModel):
    name: str
    description: Optional[str] = None
    duration: int # in minutes
    price: float
    currency: str = "USD"

class ServiceCreate(ServiceBase):
    pass

class Service(ServiceBase):
    id: Optional[int] = None # Assuming services will have an ID in a more complex setup
    class Config:
        from_attributes = True

class AvailabilitySlot(BaseModel):
    day_of_week: str # e.g., "Monday"
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
    # services_json: Optional[str] = Field("[]", alias="services", validation_alias="services") # To be handled separately or as a list of ServiceCreate
    # availability_json: Optional[str] = Field("{}", alias="availability", validation_alias="availability") # To be handled separately or as a dict of AvailabilitySlot

class OwnerInDBBase(OwnerBase):
    id: int
    services_json: str
    availability_json: str
    # services: List[Service] = [] # This would require parsing services_json
    # availability: Dict[str, List[AvailabilitySlot]] = {} # This would require parsing availability_json

    class Config:
        from_attributes = True

class Owner(OwnerInDBBase):
    pass

class OwnerWithPassword(OwnerInDBBase):
    hashed_password: str

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
    booking_timestamp: datetime
    status: str

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None