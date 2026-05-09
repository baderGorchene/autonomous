from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import List, Dict, Optional
from datetime import datetime, time

class Service(BaseModel):
    name: str
    duration_minutes: int
    price: float

class Availability(BaseModel):
    day_of_week: int
    start_time: time
    end_time: time

    @field_validator('end_time')
    def end_after_start(cls, v, info):
        start = info.data.get('start_time')
        if start and v <= start:
            raise ValueError('end_time must be after start_time')
        return v

class OwnerCreate(BaseModel):
    name: str
    email: EmailStr
    business_name: str
    slug: str
    services: List[Service]
    availability: List[Availability]

class BookingCreate(BaseModel):
    customer_name: str
    customer_email: EmailStr
    customer_phone: str
    service_name: str
    datetime: datetime

class BookingResponse(BookingCreate):
    id: int
    owner_id: int
    status: str
    created_at: datetime

    class Config:
        from_attributes = True