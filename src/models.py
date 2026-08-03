from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from .database import Base

class Owner(Base):
    __tablename__ = "owners"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    business_name = Column(String, index=True)
    slug = Column(String, unique=True, index=True) # For public booking page URL
    services_json = Column(Text) # JSON string of services offered
    availability_json = Column(Text) # JSON string of availability
    phone = Column(String, nullable=True) # Owner's phone number

    bookings = relationship("Booking", back_populates="owner")

class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("owners.id"))
    customer_name = Column(String)
    customer_email = Column(String)
    customer_phone = Column(String, nullable=True) # Customer's phone number
    service_name = Column(String) # Name of the booked service
    booking_date = Column(String) # YYYY-MM-DD
    booking_time = Column(String) # HH:MM
    booking_timestamp = Column(DateTime, default=datetime.utcnow) # When the booking was made
    status = Column(String, default="confirmed") # e.g., confirmed, cancelled

    owner = relationship("Owner", back_populates="bookings")