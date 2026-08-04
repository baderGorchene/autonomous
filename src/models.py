from sqlalchemy import Column, Integer, String, Boolean, DateTime
from src.database import Base
import datetime

class Owner(Base):
    __tablename__ = "owners"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    business_name = Column(String)
    slug = Column(String, unique=True, index=True)
    services_json = Column(String) # JSON string for services
    availability_json = Column(String) # JSON string for availability
    phone = Column(String, nullable=True) # Added phone for owner

class Booking(Base):
    __tablename__ = "bookings"
    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, index=True)
    customer_name = Column(String)
    customer_email = Column(String)
    customer_phone = Column(String, nullable=True) # Added customer phone
    service_name = Column(String)
    booking_date = Column(DateTime)
    booking_time = Column(String) # e.g., "09:00 AM"
    status = Column(String, default="confirmed")
    created_at = Column(DateTime, default=datetime.datetime.now)