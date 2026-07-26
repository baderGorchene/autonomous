from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from .database import Base
import datetime

class Owner(Base):
    __tablename__ = "owners"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    is_active = Column(Boolean, default=True)
    name = Column(String, index=True)
    business_name = Column(String, index=True)
    slug = Column(String, unique=True, index=True) # For public booking page URL
    services_json = Column(Text) # Store services as JSON string
    availability_json = Column(Text) # Store availability as JSON string
    phone = Column(String, nullable=True) # Owner's phone number

    bookings = relationship("Booking", back_populates="owner")

class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("owners.id"))
    customer_name = Column(String, index=True)
    customer_email = Column(String, index=True)
    customer_phone = Column(String, nullable=True) # Customer's phone number
    service_name = Column(String)
    booking_date = Column(DateTime)
    booking_time = Column(String) # Stored as HH:MM string for flexibility
    notes = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.now)

    owner = relationship("Owner", back_populates="bookings")
