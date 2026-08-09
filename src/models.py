from sqlalchemy import Column, Integer, String, Date, Time, ForeignKey, Boolean, Enum as SQLEnum, DateTime
from sqlalchemy.orm import relationship
from .database import Base
import enum
from datetime import datetime

class RecurrenceType(enum.Enum):
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"

class Owner(Base):
    __tablename__ = "owners"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    name = Column(String)
    phone = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    services = relationship("Service", back_populates="owner")
    bookings = relationship("Booking", back_populates="owner")
    availabilities = relationship("Availability", back_populates="owner")
    subscriptions = relationship("Subscription", back_populates="owner")

class Service(Base):
    __tablename__ = "services"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("owners.id"))
    name = Column(String, index=True)
    description = Column(String, nullable=True)
    duration_minutes = Column(Integer)
    price = Column(Integer) # Store in cents/smallest unit
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    owner = relationship("Owner", back_populates="services")
    bookings = relationship("Booking", back_populates="service")
    availabilities = relationship("Availability", back_populates="service")

class Availability(Base):
    __tablename__ = "availabilities"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("owners.id"))
    service_id = Column(Integer, ForeignKey("services.id"), nullable=True) # If None, applies to all services
    date = Column(Date, nullable=True) # For one-off availability. If None, it's recurring.
    start_time = Column(Time)
    end_time = Column(Time)
    is_active = Column(Boolean, default=True)

    # Recurrence fields
    recurrence_type = Column(SQLEnum(RecurrenceType), nullable=True)
    recurrence_value = Column(String, nullable=True) # e.g., "MON,WED,FRI" for weekly, "15" for monthly
    recurrence_start_date = Column(Date, nullable=True) # When recurrence starts
    recurrence_end_date = Column(Date, nullable=True) # When recurrence ends

    owner = relationship("Owner", back_populates="availabilities")
    service = relationship("Service", back_populates="availabilities")

class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("owners.id"))
    service_id = Column(Integer, ForeignKey("services.id"))
    customer_name = Column(String, index=True)
    customer_email = Column(String)
    customer_phone = Column(String, nullable=True)
    date = Column(Date, index=True)
    time = Column(Time)
    status = Column(String, default="confirmed") # e.g., confirmed, cancelled
    created_at = Column(DateTime, default=datetime.utcnow)

    # Recurrence fields for the booking itself (if this booking represents a recurring series)
    is_recurring = Column(Boolean, default=False)
    recurrence_type = Column(SQLEnum(RecurrenceType), nullable=True)
    recurrence_value = Column(String, nullable=True) # e.g., "MON,WED,FRI" for weekly, "15" for monthly
    recurrence_end_date = Column(Date, nullable=True)
    parent_booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=True) # For individual occurrences of a recurring series

    owner = relationship("Owner", back_populates="bookings")
    service = relationship("Service", back_populates="bookings")
    # Optional: self-referential relationship for parent/child bookings
    recurring_children = relationship("Booking", backref="parent_booking", remote_side=[id])

class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("owners.id"))
    stripe_customer_id = Column(String, unique=True, index=True)
    stripe_subscription_id = Column(String, unique=True, index=True)
    current_plan_id = Column(String) # e.g., Stripe Price ID
    status = Column(String, default="active") # e.g., active, cancelled, past_due
    start_date = Column(DateTime, default=datetime.utcnow)
    end_date = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    owner = relationship("Owner", back_populates="subscriptions")
