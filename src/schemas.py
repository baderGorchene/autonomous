from pydantic import BaseModel, EmailStr, Field
from datetime import datetime, time, date
from typing import Optional, List

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None

class OwnerBase(BaseModel):
    email: EmailStr
    name: Optional[str] = None
    phone: Optional[str] = None
    whatsapp_number: Optional[str] = None
    currency: Optional[str] = "USD"
    locale: Optional[str] = "en"

class OwnerCreate(OwnerBase):
    password: str

class OwnerUpdate(OwnerBase):
    email: Optional[EmailStr] = None
    password: Optional[str] = None
    name: Optional[str] = None
    phone: Optional[str] = None
    whatsapp_number: Optional[str] = None
    currency: Optional[str] = None
    locale: Optional[str] = None

class Owner(OwnerBase):
    id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
    stripe_customer_id: Optional[str] = None
    subscription_status: str
    
    services: List["Service"] = []
    bookings: List["Booking"] = []
    recurring_availability_rules: List["RecurringAvailabilityRule"] = []

    class Config:
        from_attributes = True

class ServiceBase(BaseModel):
    name: str
    description: Optional[str] = None
    duration_minutes: int = Field(..., gt=0)
    price: int = Field(..., ge=0) # Price in cents
    is_active: bool = True

class ServiceCreate(ServiceBase):
    pass

class ServiceUpdate(ServiceBase):
    name: Optional[str] = None
    description: Optional[str] = None
    duration_minutes: Optional[int] = None
    price: Optional[int] = None
    is_active: Optional[bool] = None

class Service(ServiceBase):
    id: int
    owner_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class BookingBase(BaseModel):
    owner_id: int
    customer_name: str
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    booking_time: datetime
    service_name: str # Denormalized for easier display
    service_duration: int
    service_price: int

class BookingCreate(BookingBase):
    pass

class BookingUpdate(BookingBase):
    customer_name: Optional[str] = None
    customer_email: Optional[EmailStr] = None
    customer_phone: Optional[str] = None
    booking_time: Optional[datetime] = None
    status: Optional[str] = None

class Booking(BookingBase):
    id: int
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class RecurringAvailabilityRuleBase(BaseModel):
    rrule_string: str
    rule_start_date: date
    rule_end_date: Optional[date] = None
    start_time: time
    end_time: time
    slot_duration: int = 30
    is_active: bool = True

class RecurringAvailabilityRuleCreate(RecurringAvailabilityRuleBase):
    pass

class RecurringAvailabilityRuleUpdate(RecurringAvailabilityRuleBase):
    rrule_string: Optional[str] = None
    rule_start_date: Optional[date] = None
    rule_end_date: Optional[date] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    slot_duration: Optional[int] = None
    is_active: Optional[bool] = None

class RecurringAvailabilityRule(RecurringAvailabilityRuleBase):
    id: int
    owner_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

# Forward references for type hints
Owner.model_rebuild()
Service.model_rebuild()
Booking.model_rebuild()
