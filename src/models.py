from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, Time, Text, Date
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime, time, date

Base = declarative_base()

class Owner(Base):
    __tablename__ = "owners"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    is_active = Column(Boolean, default=True)
    name = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    whatsapp_number = Column(String, nullable=True)
    currency = Column(String, default="USD")
    locale = Column(String, default="en")
    stripe_customer_id = Column(String, nullable=True)
    subscription_status = Column(String, default="free") # 'free', 'premium', 'canceled'
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    services = relationship("Service", back_populates="owner")
    bookings = relationship("Booking", back_populates="owner")
    recurring_availability_rules = relationship("RecurringAvailabilityRule", back_populates="owner")

class Service(Base):
    __tablename__ = "services"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("owners.id"))
    name = Column(String, index=True)
    description = Column(String, nullable=True)
    duration_minutes = Column(Integer)
    price = Column(Integer) # Price in cents
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    owner = relationship("Owner", back_populates="services")

class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("owners.id"))
    customer_name = Column(String)
    customer_email = Column(String)
    customer_phone = Column(String, nullable=True)
    booking_time = Column(DateTime, index=True)
    service_name = Column(String) # Denormalized for easier display
    service_duration = Column(Integer)
    service_price = Column(Integer)
    status = Column(String, default="confirmed") # e.g., 'confirmed', 'canceled', 'completed'
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    owner = relationship("Owner", back_populates="bookings")

class RecurringAvailabilityRule(Base):
    __tablename__ = "recurring_availability_rules"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("owners.id"))
    rrule_string = Column(Text, nullable=False) # Stores the RRULE string, e.g., "FREQ=WEEKLY;BYDAY=MO,WE,FR"
    rule_start_date = Column(Date, nullable=False) # When this rule effectively starts applying
    rule_end_date = Column(Date, nullable=True) # When this rule effectively stops applying (optional)
    start_time = Column(Time, nullable=False)   # Start time of availability on the recurring days
    end_time = Column(Time, nullable=False)     # End time of availability on the recurring days
    slot_duration = Column(Integer, default=30) # Duration of each bookable slot in minutes
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    owner = relationship("Owner", back_populates="recurring_availability_rules")
