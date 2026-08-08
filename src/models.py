from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Float
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()

class Owner(Base):
    __tablename__ = "owners"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    is_active = Column(Boolean, default=True)
    name = Column(String)
    phone = Column(String, nullable=True)
    locale = Column(String, default="en")

    services = relationship("Service", back_populates="owner")
    bookings = relationship("Booking", back_populates="owner")

class Service(Base):
    __tablename__ = "services"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    description = Column(String, nullable=True)
    duration_minutes = Column(Integer)
    price = Column(Float) # Added price for payment
    owner_id = Column(Integer, ForeignKey("owners.id"))

    owner = relationship("Owner", back_populates="services")
    availability_slots = relationship("AvailabilitySlot", back_populates="service")
    bookings = relationship("Booking", back_populates="service")

class AvailabilitySlot(Base):
    __tablename__ = "availability_slots"

    id = Column(Integer, primary_key=True, index=True)
    service_id = Column(Integer, ForeignKey("services.id"))
    day_of_week = Column(Integer)
    start_time = Column(String)
    end_time = Column(String)

    service = relationship("Service", back_populates="availability_slots")

class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("owners.id"))
    service_id = Column(Integer, ForeignKey("services.id"))
    customer_name = Column(String)
    customer_email = Column(String)
    customer_phone = Column(String, nullable=True)
    booking_time = Column(DateTime)
    status = Column(String, default="pending") # e.g., "pending", "confirmed", "cancelled", "paid", "payment_failed"
    created_at = Column(DateTime, default=datetime.utcnow)

    owner = relationship("Owner", back_populates="bookings")
    service = relationship("Service", back_populates="bookings")
    payment = relationship("Payment", back_populates="booking", uselist=False, cascade="all, delete-orphan") # One-to-one with Payment

class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"), unique=True) # One-to-one
    stripe_payment_intent_id = Column(String, unique=True, index=True)
    amount = Column(Integer) # Stored in cents
    currency = Column(String, default="usd")
    status = Column(String, default="requires_payment_method") # e.g., "requires_payment_method", "requires_confirmation", "succeeded", "failed"
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    booking = relationship("Booking", back_populates="payment")
