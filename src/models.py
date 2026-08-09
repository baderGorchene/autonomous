from sqlalchemy import Column, Integer, String, ForeignKey, Enum, Text, Boolean, Date, Time, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
import enum

Base = declarative_base()

class RecurrenceType(enum.Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    NONE = "none"

class Owner(Base):
    __tablename__ = "owners"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    name = Column(String)
    phone_number = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    subscription_status = Column(String, default="free") # e.g., "free", "premium", "cancelled"
    stripe_customer_id = Column(String, nullable=True, unique=True)

    services = relationship("Service", back_populates="owner")
    bookings = relationship("Booking", back_populates="owner")
    availabilities = relationship("Availability", back_populates="owner")

class Service(Base):
    __tablename__ = "services"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    description = Column(String, nullable=True)
    duration_minutes = Column(Integer)
    price = Column(Integer) # Price in cents
    owner_id = Column(Integer, ForeignKey("owners.id"))

    owner = relationship("Owner", back_populates="services")
    bookings = relationship("Booking", back_populates="service")
    availabilities = relationship("Availability", back_populates="service")

class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    email = Column(String, unique=True, index=True)
    phone_number = Column(String, unique=True, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    bookings = relationship("Booking", back_populates="customer")

class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("owners.id"))
    service_id = Column(Integer, ForeignKey("services.id"))
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True) # Optional customer account link
    customer_name = Column(String)
    customer_email = Column(String)
    customer_phone_number = Column(String, nullable=True)
    date = Column(Date)
    time = Column(Time)
    # For recurring bookings
    is_recurring = Column(Boolean, default=False)
    recurrence_id = Column(String, nullable=True) # A unique ID for a series of recurring bookings
    recurrence_type = Column(Enum(RecurrenceType), default=RecurrenceType.NONE) # DAILY, WEEKLY, MONTHLY
    recurrence_value = Column(String, nullable=True) # e.g., 'MON,WED,FRI' for weekly, '15' for monthly
    recurrence_end_date = Column(Date, nullable=True) # When the recurring series ends

    owner = relationship("Owner", back_populates="bookings")
    service = relationship("Service", back_populates="bookings")
    customer = relationship("Customer", back_populates="bookings")

class Availability(Base):
    __tablename__ = "availabilities"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("owners.id"))
    service_id = Column(Integer, ForeignKey("services.id"), nullable=True) # If None, applies to all services
    date = Column(Date, nullable=True) # Specific date for one-off, None for recurring
    start_time = Column(Time)
    end_time = Column(Time)
    # For recurring availability
    recurrence_type = Column(Enum(RecurrenceType), default=RecurrenceType.NONE)
    recurrence_value = Column(String, nullable=True) # e.g., 'MON,WED,FRI' for weekly, '15' for monthly
    recurrence_start_date = Column(Date, nullable=True)
    recurrence_end_date = Column(Date, nullable=True)

    owner = relationship("Owner", back_populates="availabilities")
    service = relationship("Service", back_populates="availabilities")
