from pydantic import BaseModel, EmailStr, Field, model_validator
from datetime import datetime, date, time, timedelta
from typing import Optional, List
import uuid

class OwnerBase(BaseModel):
    email: EmailStr
    full_name: Optional[str] = None
    phone_number: Optional[str] = None

class OwnerCreate(OwnerBase):
    password: str

class OwnerInDB(OwnerBase):
    id: uuid.UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime
    locale: str
    currency: str
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None
    subscription_status: str
    subscription_ends_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class Owner(OwnerInDB):
    pass

class ServiceBase(BaseModel):
    name: str = Field(..., min_length=1)
    description: Optional[str] = None
    duration_minutes: int = Field(..., gt=0)
    price: int = Field(..., ge=0) # Price in smallest unit (e.g., cents)

class ServiceCreate(ServiceBase):
    pass

class ServiceInDB(ServiceBase):
    id: uuid.UUID
    owner_id: uuid.UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class Service(ServiceInDB):
    pass

class AvailabilityBase(BaseModel):
    day_of_week: int = Field(..., ge=0, le=6) # 0=Monday, 6=Sunday
    start_time: time
    end_time: time

class AvailabilityCreate(AvailabilityBase):
    pass

class AvailabilityInDB(AvailabilityBase):
    id: uuid.UUID
    owner_id: uuid.UUID
    is_available: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class Availability(AvailabilityInDB):
    pass

class BookingCreate(BaseModel):
    service_id: uuid.UUID
    customer_name: str = Field(..., min_length=1)
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    start_time: datetime # This will be the start time of the *first* booking if recurring
    
    is_recurring: bool = False
    recurrence_pattern: Optional[str] = None # e.g., "DAILY", "WEEKLY", "MONTHLY"
    recurrence_ends_on: Optional[date] = None # End date for recurrence
    recurrence_count: Optional[int] = None # Number of occurrences
    
    @model_validator(mode='after')
    def validate_recurrence_fields(self) -> 'BookingCreate':
        if self.is_recurring:
            if not self.recurrence_pattern:
                raise ValueError("recurrence_pattern is required for recurring bookings")
            
            if self.recurrence_pattern not in ["DAILY", "WEEKLY", "MONTHLY"]:
                raise ValueError("Invalid recurrence_pattern. Must be DAILY, WEEKLY, or MONTHLY.")

            if not (self.recurrence_ends_on or self.recurrence_count):
                raise ValueError("Either recurrence_ends_on or recurrence_count is required for recurring bookings")
            if self.recurrence_ends_on and self.recurrence_count:
                raise ValueError("Cannot specify both recurrence_ends_on and recurrence_count")
            
            if self.recurrence_ends_on and self.recurrence_ends_on < self.start_time.date():
                raise ValueError("Recurrence end date cannot be before the start date.")
            if self.recurrence_count is not None and self.recurrence_count <= 0:
                raise ValueError("Recurrence count must be a positive integer.")

        return self

class BookingResponse(BaseModel):
    id: uuid.UUID
    owner_id: uuid.UUID
    service_id: uuid.UUID
    customer_name: str
    customer_email: EmailStr
    customer_phone: Optional[str]
    start_time: datetime
    end_time: datetime
    status: str
    created_at: datetime
    updated_at: datetime
    recurrence_id: Optional[uuid.UUID]
    is_master_booking: bool
    recurrence_pattern: Optional[str]
    recurrence_end_date: Optional[date]
    recurrence_count: Optional[int]

    class Config:
        from_attributes = True
