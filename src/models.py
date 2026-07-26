from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from .database import Base
from datetime import datetime

class Owner(Base):
    __tablename__ = "owners"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    business_name = Column(String)
    slug = Column(String, unique=True, index=True) # For public booking page URL
    services_json = Column(Text) # JSON string of services offered
    availability_json = Column(Text) # JSON string of availability
    phone = Column(String, nullable=True) # Owner's phone number for notifications

    bookings = relationship("Booking", back_populates="owner")

class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("owners.id"))
    customer_name = Column(String, index=True)
    customer_email = Column(String, index=True)
    customer_phone = Column(String, nullable=True)
    service_name = Column(String)
    booking_time = Column(DateTime)
    service_duration_minutes = Column(Integer, default=30)
    created_at = Column(DateTime, default=datetime.now)

    owner = relationship("Owner", back_populates="bookings")
