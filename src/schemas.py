from datetime import datetime, date, timedelta
from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field

class ServiceBase(BaseModel):
    name: str
    description: Optional[str] = None
    duration_minutes: int
    price: float

class ServiceCreate(ServiceBase):
    pass

class Service(ServiceBase):
    id: int
    owner_id: int
    is_active: bool = True

    class Config:
        from_attributes = True

class OwnerBase(BaseModel):
    email: EmailStr
    business_name: str
    phone_number: Optional[str] = None
    default_locale: str = "en"

class OwnerCreate(OwnerBase):
    password: str

class Owner(OwnerBase):
    id: int
    is_active: bool = True
    services: List[Service] = []

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None

class BookingBase(BaseModel):
    service_id: int
    customer_name: str
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    start_time: datetime
    end_time: datetime
    status: str = "pending"

class BookingCreate(BookingBase):
    pass

class Booking(BookingBase):
    id: int
    owner_id: int
    service: Service
    recurrence_group_id: Optional[str] = None

    class Config:
        from_attributes = True

class RecurringBookingCreate(BaseModel):
    service_id: int
    customer_name: str
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    first_occurrence_start_time: datetime
    duration_minutes: int
    recurrence_type: str = Field(..., description="e.g., daily, weekly, monthly")
    recurrence_interval: int = Field(1, ge=1, description="Interval for recurrence (e.g., 2 for every other week)")
    recurrence_end_date: Optional[date] = None
    number_of_occurrences: Optional[int] = None

    class Config:
        extra = "forbid"
        json_schema_extra = {
            "example": {
                "service_id": 1,
                "customer_name": "John Doe",
                "customer_email": "john.doe@example.com",
                "customer_phone": "+1234567890",
                "first_occurrence_start_time": "2023-10-27T10:00:00Z",
                "duration_minutes": 60,
                "recurrence_type": "weekly",
                "recurrence_interval": 1,
                "number_of_occurrences": 4
            }
        }
