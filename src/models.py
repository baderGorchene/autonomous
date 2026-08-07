from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, Date, Time
from sqlalchemy.orm import relationship
from datetime import datetime

# Assuming Base is imported from src.database
from .database import Base

class Owner(Base):
    __tablename__ = "owners"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    is_active = Column(Boolean, default=True)
    business_name = Column(String)
    slug = Column(String, unique=True, index=True) # For bookslot.app/their-name
    services_json = Column(String, default="[]") # Stores JSON string of services
    availability_json = Column(String, default="{}") # Stores JSON string of availability
    phone = Column(String, nullable=True) # Added based on completed steps

    bookings = relationship("Booking", back_populates="owner")

class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("owners.id"))
    customer_name = Column(String)
    customer_email = Column(String)
    customer_phone = Column(String, nullable=True) # Added based on completed steps
    service_name = Column(String)
    booking_date = Column(Date)
    booking_time = Column(Time)
    created_at = Column(DateTime, default=datetime.now)

    owner = relationship("Owner", back_populates="bookings")
