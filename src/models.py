from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from .database import Base
import datetime

class Owner(Base):
    __tablename__ = "owners"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    business_name = Column(String)
    slug = Column(String, unique=True, index=True) # For public booking page URL
    services_json = Column(Text) # JSON string of services offered
    availability_json = Column(Text) # JSON string of weekly availability
    phone = Column(String, nullable=True) # Owner's phone number

    bookings = relationship("Booking", back_populates="owner")

class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("owners.id"))
    customer_name = Column(String, index=True)
    customer_email = Column(String, index=True)
    customer_phone = Column(String, nullable=True) # Customer's phone number
    service_name = Column(String) # Name of the service booked
    booking_date = Column(DateTime)
    booking_time = Column(String) # e.g., "09:00"
    status = Column(String, default="pending") # e.g., "pending", "confirmed", "cancelled"
    
    owner = relationship("Owner", back_populates="bookings")

