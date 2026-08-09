from pydantic import BaseModel, EmailStr, Field
from datetime import datetime, date
from typing import Optional, List, Literal

# Define Literal for recurrence patterns
RecurrencePatternLiteral = Literal["daily", "weekly", "bi-weekly", "monthly"]

class BookingBase(BaseModel):
    service_id: int
    customer_name: str
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    booking_date: date
    start_time: str # "HH:MM"
    # New fields for recurring bookings
    is_recurring: bool = False
    recurrence_pattern: Optional[RecurrencePatternLiteral] = None
    recurrence_end_date: Optional[date] = None

class BookingCreate(BookingBase):
    pass

class BookingResponse(BookingBase):
    id: int
    owner_id: int
    end_time: str
    status: str
    created_at: datetime
    parent_booking_id: Optional[int] = None # Added for recurring instances

    class Config:
        from_attributes = True
