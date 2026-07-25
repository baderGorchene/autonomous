from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from .database import Base
import datetime

class Owner(Base):
    __tablename__ = "owners"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    name = Column(String)
    business_name = Column(String)
    slug = Column(String, unique=True, index=True)
    phone = Column(String, nullable=True) # Added phone number
    services_json = Column(Text) # Stores JSON string of services
    availability_json = Column(Text) # Stores JSON string of availability
    is_active = Column(Boolean, default=True)

    bookings = relationship("Booking", back_populates="owner")

class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("owners.id"))
    customer_name = Column(String)
    customer_email = Column(String)
    customer_phone = Column(String, nullable=True) # Added customer phone number
    service_name = Column(String)
    booking_date = Column(DateTime)
    booking_time = Column(String) # e.g., "09:00"
    status = Column(String, default="pending") # e.g., pending, confirmed, cancelled

    owner = relationship("Owner", back_populates="bookings")
