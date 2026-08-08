from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, Float
from sqlalchemy.orm import relationship
from .database import Base
from datetime import datetime

class Owner(Base):
    __tablename__ = "owners"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    is_active = Column(Boolean, default=True)
    name = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    subscription_status = Column(String, default="free") # 'free', 'premium', 'cancelled'
    stripe_customer_id = Column(String, nullable=True)
    stripe_subscription_id = Column(String, nullable=True)
    is_admin = Column(Boolean, default=False) # New field for admin panel

    services = relationship("Service", back_populates="owner")
    availabilities = relationship("Availability", back_populates="owner")
    bookings = relationship("Booking", back_populates="owner")

class Service(Base):
    __tablename__ = "services"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    description = Column(String, nullable=True)
    duration_minutes = Column(Integer)
    price = Column(Float)
    owner_id = Column(Integer, ForeignKey("owners.id"))

    owner = relationship("Owner", back_populates="services")
    bookings = relationship("Booking", back_populates="service")

class Availability(Base):
    __tablename__ = "availabilities"

    id = Column(Integer, primary_key=True, index=True)
    day_of_week = Column(Integer, index=True) # 0-6 for Monday-Sunday
    start_time = Column(String) # HH:MM
    end_time = Column(String)   # HH:MM
    owner_id = Column(Integer, ForeignKey("owners.id"))

    owner = relationship("Owner", back_populates="availabilities")

class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    customer_name = Column(String)
    customer_email = Column(String)
    customer_phone = Column(String, nullable=True)
    booking_time = Column(DateTime, default=datetime.utcnow)
    service_id = Column(Integer, ForeignKey("services.id"))
    owner_id = Column(Integer, ForeignKey("owners.id")) # Denormalized for easier query
    locale = Column(String, default="en") # For i18n confirmation emails

    service = relationship("Service", back_populates="bookings")
    owner = relationship("Owner", back_populates="bookings")
