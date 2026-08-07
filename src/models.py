from sqlalchemy import Column, Integer, String, Boolean, Date, Time, ForeignKey, Float
from sqlalchemy.orm import relationship
from .database import Base

class Owner(Base):
    __tablename__ = "owners"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    name = Column(String)
    business_name = Column(String)
    slug = Column(String, unique=True, index=True)
    services_json = Column(String, default="[]") # Stores JSON list of services with duration
    availability_json = Column(String, default="{}") # Stores JSON dict of availability
    phone = Column(String, nullable=True) # Added for WhatsApp notifications
    is_active = Column(Boolean, default=True)

    bookings = relationship("Booking", back_populates="owner")

class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    customer_name = Column(String, index=True)
    customer_email = Column(String)
    customer_phone = Column(String, nullable=True) # Added for WhatsApp notifications
    service_name = Column(String)
    service_duration_minutes = Column(Integer) # NEW COLUMN: Duration of the booked service
    booking_date = Column(Date, index=True)
    booking_time = Column(Time, index=True)
    owner_id = Column(Integer, ForeignKey("owners.id"))

    owner = relationship("Owner", back_populates="bookings")
