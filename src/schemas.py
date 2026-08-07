from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from typing import List, Optional

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None

class OwnerBase(BaseModel):
    name: str
    email: EmailStr
    phone: Optional[str] = None
    locale: str = "en"

class OwnerCreate(OwnerBase):
    password: str = Field(..., min_length=8)

class OwnerUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    locale: Optional[str] = None

class OwnerInDB(OwnerBase):
    id: int
    hashed_password: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    stripe_customer_id: Optional[str] = None
    is_premium_subscriber: bool = False

    class Config:
        from_attributes = True

class OwnerResponse(OwnerBase):
    id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
    is_premium_subscriber: bool

    class Config:
        from_attributes = True

class OwnerLogin(BaseModel):
    email: EmailStr
    password: str

class ServiceBase(BaseModel):
    name: str
    description: Optional[str] = None
    duration_minutes: int = Field(..., gt=0)
    price: int = Field(..., ge=0)

class ServiceCreate(ServiceBase):
    pass

class ServiceUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    duration_minutes: Optional[int] = Field(None, gt=0)
    price: Optional[int] = Field(None, ge=0)

class ServiceResponse(ServiceBase):
    id: int
    owner_id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class AvailabilityBase(BaseModel):
    day_of_week: int = Field(..., ge=0, le=6)
    start_time_minutes: int = Field(..., ge=0, lt=1440)
    end_time_minutes: int = Field(..., ge=0, lt=1440)

class AvailabilityCreate(AvailabilityBase):
    pass

class AvailabilityResponse(AvailabilityBase):
    id: int
    service_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class BookingBase(BaseModel):
    customer_name: str
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    booking_time: datetime

class BookingCreate(BookingBase):
    service_id: int

class BookingResponse(BookingBase):
    id: int
    owner_id: int
    service_id: int
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class UpcomingBooking(BaseModel):
    id: int
    service_name: str
    customer_name: str
    customer_email: EmailStr
    customer_phone: Optional[str]
    booking_time: datetime
    status: str

    class Config:
        from_attributes = True

class HTTPError(BaseModel):
    detail: str

    class Config:
        schema_extra = {
            "example": {"detail": "HTTPException details"},
        }

class StripeCheckoutSessionResponse(BaseModel):
    session_id: str
    session_url: str

class StripeWebhookEventData(BaseModel):
    object: dict

class StripeWebhookEvent(BaseModel):
    id: str
    object: str
    api_version: str
    created: int
    data: StripeWebhookEventData
    livemode: bool
    pending_webhooks: int
    request: Optional[dict] = None
    type: str