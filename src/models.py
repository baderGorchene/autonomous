from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from .database import Base
import datetime

class Owner(Base):
    __tablename__ = "owners"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    business_name = Column(String, index=True)
    slug = Column(String, unique=True, index=True) # e.g., bookslot.app/their-name
    phone = Column(String, nullable=True) # Added in previous step
    services_json = Column(Text) # Stored as JSON string
    availability_json = Column(Text) # Stored as JSON string

    bookings = relationship("Booking", back_populates="owner")

class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("owners.id"))
    customer_name = Column(String)
    customer_email = Column(String)
    customer_phone = Column(String, nullable=True) # Added in previous step
    service_name = Column(String)
    booking_time = Column(DateTime)
    created_at = Column(DateTime, default=datetime.datetime.now)

    owner = relationship("Owner", back_populates="bookings")