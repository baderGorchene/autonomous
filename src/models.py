from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, Date, Time
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
    services_json = Column(String, default="[]") # JSON string of services offered
    availability_json = Column(String, default="{}") # JSON string of availability
    phone = Column(String, nullable=True) # Added phone number

    bookings = relationship("Booking", back_populates="owner")

class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("owners.id"))
    customer_name = Column(String)
    customer_email = Column(String)
    customer_phone = Column(String, nullable=True) # Added customer phone number
    service_name = Column(String)
    booking_date = Column(Date)
    booking_time = Column(Time)
    notes = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.now)

    owner = relationship("Owner", back_populates="bookings")
