import uuid
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Date, ForeignKey, Time
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy import func
from datetime import datetime, date, time

from .database import Base

# Use a generic UUID type for SQLite compatibility if PG_UUID is not available
# Assuming environment might be SQLite for development, Postgres for production
# In a real scenario, this would be set up more robustly (e.g., via config or ORM dialect detection)
UUID = PG_UUID if hasattr(Base.metadata.bind, 'name') and Base.metadata.bind.name == 'postgresql' else String(36)

class Owner(Base):
    __tablename__ = "owners"

    id = Column(UUID, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    full_name = Column(String, nullable=True)
    phone_number = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    locale = Column(String, default="en")
    currency = Column(String, default="USD")

    stripe_customer_id = Column(String, nullable=True, unique=True)
    stripe_subscription_id = Column(String, nullable=True, unique=True)
    subscription_status = Column(String, default="free")
    subscription_ends_at = Column(DateTime, nullable=True)

    services = relationship("Service", back_populates="owner")
    availabilities = relationship("Availability", back_populates="owner")
    bookings = relationship("Booking", back_populates="owner")

class Service(Base):
    __tablename__ = "services"

    id = Column(UUID, primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_id = Column(UUID, ForeignKey("owners.id"))
    name = Column(String, index=True)
    description = Column(String, nullable=True)
    duration_minutes = Column(Integer)
    price = Column(Integer)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    owner = relationship("Owner", back_populates="services")
    bookings = relationship("Booking", back_populates="service")

class Availability(Base):
    __tablename__ = "availabilities"

    id = Column(UUID, primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_id = Column(UUID, ForeignKey("owners.id"))
    day_of_week = Column(Integer) # 0=Monday, 6=Sunday
    start_time = Column(Time)
    end_time = Column(Time)
    is_available = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    owner = relationship("Owner", back_populates="availabilities")

class Booking(Base):
    __tablename__ = "bookings"

    id = Column(UUID, primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_id = Column(UUID, ForeignKey("owners.id"))
    service_id = Column(UUID, ForeignKey("services.id"))
    customer_name = Column(String)
    customer_email = Column(String)
    customer_phone = Column(String, nullable=True)
    start_time = Column(DateTime)
    end_time = Column(DateTime)
    status = Column(String, default="confirmed") # confirmed, cancelled, completed
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Recurring booking fields
    recurrence_id = Column(UUID, nullable=True, index=True) # Group ID for recurring bookings
    is_master_booking = Column(Boolean, default=False) # True if this is the "template" booking
    recurrence_pattern = Column(String, nullable=True) # e.g., "DAILY", "WEEKLY", "MONTHLY"
    recurrence_end_date = Column(Date, nullable=True) # The actual end date of the recurring sequence
    recurrence_count = Column(Integer, nullable=True) # Total count for the recurrence group

    owner = relationship("Owner", back_populates="bookings")
    service = relationship("Service", back_populates="bookings")
