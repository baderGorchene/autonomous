from pydantic import BaseModel, EmailStr, Field
from datetime import datetime, timedelta
from typing import Optional, List
import uuid

class OwnerBase(BaseModel):
    email: EmailStr
    name: str
    phone: Optional[str] = None

class OwnerCreate(OwnerBase):
    password: str

class OwnerInDB(OwnerBase):
    id: uuid.UUID
    is_active: bool
    created_at: datetime
    stripe_customer_id: Optional[str] = None
    subscription_status: str

    class Config:
        from_attributes = True

class ServiceBase(BaseModel):
    name: str
    description: Optional[str] = None
    duration_minutes: int = Field(..., gt=0)
    price: int = Field(..., ge=0)

class ServiceCreate(ServiceBase):
    pass

class ServiceInDB(ServiceBase):
    id: uuid.UUID
    owner_id: uuid.UUID
    is_active: bool

    class Config:
        from_attributes = True

class AvailabilityBase(BaseModel):
    day_of_week: int = Field(..., ge=0, le=6, description="0=Monday, 6=Sunday")
    start_time: str = Field(..., pattern=r"^\\d{2}:\\d{2}$", description="HH:MM format")
    end_time: str = Field(..., pattern=r"^\\d{2}:\\d{2}$", description="HH:MM format")

class AvailabilityCreate(AvailabilityBase):
    pass

class AvailabilityInDB(AvailabilityBase):
    id: uuid.UUID
    owner_id: uuid.UUID

    class Config:
        from_attributes = True

class BookingBase(BaseModel):
    service_id: uuid.UUID
    customer_name: str
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    start_time: datetime
    end_time: datetime

class BookingCreate(BookingBase):
    is_recurring: bool = False
    recurrence_pattern: Optional[str] = None
    recurrence_end_date: Optional[datetime] = None
    recurrence_count: Optional[int] = None

    class Config:
        json_schema_extra = {
            "example": {
                "service_id": "123e4567-e89b-12d3-a456-426614174000",
                "customer_name": "John Doe",
                "customer_email": "john.doe@example.com",
                "customer_phone": "+1234567890",
                "start_time": "2023-10-27T10:00:00Z",
                "end_time": "2023-10-27T11:00:00Z",
                "is_recurring": True,
                "recurrence_pattern": "WEEKLY",
                "recurrence_end_date": "2023-11-27T11:00:00Z",
                "recurrence_count": None
            }
        }


class BookingInDB(BookingBase):
    id: uuid.UUID
    owner_id: uuid.UUID
    status: str
    created_at: datetime
    is_recurring: bool
    recurrence_pattern: Optional[str] = None
    recurrence_end_date: Optional[datetime] = None
    recurrence_count: Optional[int] = None
    recurrence_group_id: Optional[uuid.UUID] = None

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None

class BookingCount(BaseModel):
    date: str
    count: int

class PopularService(BaseModel):
    service_name: str
    booking_count: int

class AnalyticsData(BaseModel):
    monthly_bookings: List[BookingCount]
    popular_services: List[PopularService]
