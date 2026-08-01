from pydantic import BaseModel, EmailStr, Field
from typing import List, Dict, Optional
from datetime import date, time
import json

class ServiceBase(BaseModel):
    name: str
    duration_minutes: int
    price: float

class ServiceCreate(ServiceBase):
    pass

class Service(ServiceBase):
    id: int

    class Config:
        orm_mode = True

class AvailabilitySlot(BaseModel):
    day_of_week: str # e.g., "Monday"
    start_time: time # e.g., "09:00"
    end_time: time # e.g., "17:00"

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
    is_active: bool = True
    services_json: str # JSON string of services
    availability_json: str # JSON string of availability
    
    class Config:
        orm_mode = True

class OwnerProfileUpdate(BaseModel):
    name: str
    business_name: str
    phone: Optional[str] = None
    services: Optional[List[ServiceCreate]] = None
    availability: Optional[Dict[str, List[AvailabilitySlot]]] = None # Dict of day -> list of slots

    @classmethod
    def as_form(
        cls,
        name: str = Field(...),
        business_name: str = Field(...),
        phone: Optional[str] = None,
        services_json: Optional[str] = Field(None, alias="services_json"), # Expecting a JSON string from form
        availability_json: Optional[str] = Field(None, alias="availability_json") # Expecting a JSON string from form
    ):
        services = json.loads(services_json) if services_json else None
        availability = json.loads(availability_json) if availability_json else None
        
        # Convert raw dicts from JSON to Pydantic models for validation
        parsed_services = None
        if services:
            parsed_services = [ServiceCreate(**s) for s in services]
        
        parsed_availability = None
        if availability:
            parsed_availability = {}
            for day, slots in availability.items():
                parsed_availability[day] = [AvailabilitySlot(**slot) for slot in slots]

        return cls(
            name=name,
            business_name=business_name,
            phone=phone,
            services=parsed_services,
            availability=parsed_availability
        )

class BookingBase(BaseModel):
    customer_name: str
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    service_name: str
    booking_date: date
    booking_time: time
    notes: Optional[str] = None

class BookingCreate(BookingBase):
    pass

class Booking(BookingBase):
    id: int
    owner_id: int

    class Config:
        orm_mode = True

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None
