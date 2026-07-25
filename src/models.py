from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .database import Base

class Owner(Base):
    __tablename__ = "owners"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    business_name = Column(String)
    slug = Column(String, unique=True, index=True) # For public booking page URL
    services_json = Column(Text) # Stores JSON string of services offered
    availability_json = Column(Text) # Stores JSON string of availability
    phone = Column(String, nullable=True) # Owner's phone number for WhatsApp notifications

    bookings = relationship("Booking", back_populates="owner")

class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("owners.id"))
    customer_name = Column(String)
    customer_email = Column(String)
    customer_phone = Column(String, nullable=True)
    service_name = Column(String)
    booking_time = Column(DateTime) # Store as datetime object
    status = Column(String, default="pending") # e.g., "pending", "confirmed", "cancelled"
    created_at = Column(DateTime, server_default=func.now())

    owner = relationship("Owner", back_populates="bookings")
