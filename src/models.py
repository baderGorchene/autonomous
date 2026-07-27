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
    slug = Column(String, unique=True, index=True) # For bookslot.app/their-name
    services_json = Column(Text) # JSON string of services offered
    availability_json = Column(Text) # JSON string of availability
    phone = Column(String, nullable=True) # Added for notifications

    bookings = relationship("Booking", back_populates="owner")

class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("owners.id"))
    customer_name = Column(String, index=True)
    customer_email = Column(String, index=True)
    customer_phone = Column(String, nullable=True) # Added for WhatsApp notifications
    service_name = Column(String)
    booking_time = Column(DateTime)
    duration_minutes = Column(Integer)
    is_confirmed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.now)

    owner = relationship("Owner", back_populates="bookings")
