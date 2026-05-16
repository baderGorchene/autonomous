from pydantic import BaseModel, EmailStr
from datetime import datetime

class BookingCreate(BaseModel):
    customer_name: str
    customer_email: EmailStr
    customer_phone: str
    service: str
    datetime: datetime

class OwnerPublic(BaseModel):
    business_name: str
    services: list[str]
    slug: str
