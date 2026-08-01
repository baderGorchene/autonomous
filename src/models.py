from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from .database import Base

class Owner(Base):
    __tablename__ = "owners"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    business_name = Column(String)
    slug = Column(String, unique=True, index=True)
    services_json = Column(Text) # JSON string for services
    availability_json = Column(Text) # JSON string for availability
    phone = Column(String, nullable=True) # Added phone number
    created_at = Column(DateTime, default=datetime.utcnow)

    bookings = relationship("Booking", back_populates="owner")

class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("owners.id"))
    customer_name = Column(String)
    customer_email = Column(String)
    customer_phone = Column(String, nullable=True) # Added customer phone number
    service_name = Column(String)
    booking_date = Column(String) # Stored as 'YYYY-MM-DD'
    booking_time = Column(String) # Stored as 'HH:MM'
    status = Column(String, default="confirmed") # e.g., confirmed, cancelled
    created_at = Column(DateTime, default=datetime.utcnow)

    owner = relationship("Owner", back_populates="bookings")
