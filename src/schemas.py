from datetime import date, time
from typing import Optional, List
from pydantic import BaseModel, EmailStr

class BookingBase(BaseModel):
    owner_id: int
    service_id: int
    customer_name: str
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    date: date
    time: time
    recurrence_id: Optional[int] = None # To link to a recurring series if applicable

class BookingCreate(BookingBase):
    pass

class Booking(BookingBase):
    id: int
    class Config:
        orm_mode = True

class ServiceBase(BaseModel):
    name: str
    description: Optional[str] = None
    duration_minutes: int
    price: int

class ServiceCreate(ServiceBase):
    pass

class Service(ServiceBase):
    id: int
    owner_id: int
    class Config:
        orm_mode = True

class OwnerBase(BaseModel):
    name: str
    email: EmailStr
    phone_number: Optional[str] = None
    address: Optional[str] = None

class OwnerCreate(OwnerBase):
    password: str

class Owner(OwnerBase):
    id: int
    is_premium: bool
    class Config:
        orm_mode = True
