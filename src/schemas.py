from pydantic import BaseModel
from datetime import datetime

class BookingCreate(BaseModel):
    customer_name: str
    customer_email: str
    customer_phone: str
    service: str
    datetime: datetime