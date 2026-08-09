from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, Enum, Float
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
import enum

Base = declarative_base()

class Owner(Base):
    __tablename__ = "owners"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    is_active = Column(Boolean, default=True)
    name = Column(String)
    phone = Column(String, nullable=True)
    language = Column(String, default="en")
    timezone = Column(String, default="UTC")
    currency = Column(String, default="USD")
    subscription_status = Column(String, default="free") # e.g., "free", "premium", "cancelled"
    stripe_customer_id = Column(String, nullable=True, unique=True)
    stripe_subscription_id = Column(String, nullable=True, unique=True)

    services = relationship("Service", back_populates="owner")
    availabilities = relationship("Availability", back_populates="owner")
    bookings = relationship("Booking", back_populates="owner")

class Service(Base):
    __tablename__ = "services"
    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("owners.id"))
    name = Column(String)
    description = Column(Text, nullable=True)
    duration_minutes = Column(Integer)
    price = Column(Float, default=0.0)

    owner = relationship("Owner", back_populates="services")

class Availability(Base):
    __tablename__ = "availabilities"
    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("owners.id"))
    day_of_week = Column(Integer) # 0=Monday, 6=Sunday
    start_time = Column(String) # "HH:MM"
    end_time = Column(String) # "HH:MM"

    owner = relationship("Owner", back_populates="availabilities")

class RecurrencePattern(enum.Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    BI_WEEKLY = "bi-weekly"
    MONTHLY = "monthly"

class Booking(Base):
    __tablename__ = "bookings"
    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("owners.id"))
    service_id = Column(Integer, ForeignKey("services.id"))
    customer_name = Column(String)
    customer_email = Column(String)
    customer_phone = Column(String, nullable=True)
    booking_date = Column(DateTime)
    start_time = Column(String) # "HH:MM"
    end_time = Column(String) # "HH:MM"
    status = Column(String, default="confirmed") # e.g., "confirmed", "cancelled", "pending"
    created_at = Column(DateTime, default=datetime.utcnow)

    # New fields for recurring bookings
    is_recurring = Column(Boolean, default=False)
    recurrence_pattern = Column(Enum(RecurrencePattern), nullable=True)
    recurrence_end_date = Column(DateTime, nullable=True)
    parent_booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=True) # For individual instances of a recurring series

    owner = relationship("Owner", back_populates="bookings")
    service = relationship("Service")
    
    # Self-referencing relationship for parent/child bookings
    recurring_series = relationship("Booking", remote_side=[id], backref="recurring_instances")
