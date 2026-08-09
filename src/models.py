from sqlalchemy import Column, Integer, String, Boolean, DateTime, Date, Time, Enum, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .database import Base
import enum

class RecurrenceType(enum.Enum):
    NONE = "none"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"

class Owner(Base):
    __tablename__ = "owners"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    name = Column(String, nullable=False)
    phone = Column(String, nullable=True)
    locale = Column(String, default="en")
    is_premium = Column(Boolean, default=False)
    stripe_customer_id = Column(String, nullable=True)
    stripe_subscription_id = Column(String, nullable=True)

    services = relationship("Service", back_populates="owner")
    availabilities = relationship("Availability", back_populates="owner")
    bookings = relationship("Booking", back_populates="owner")

class Service(Base):
    __tablename__ = "services"
    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("owners.id"))
    name = Column(String, index=True, nullable=False)
    description = Column(String, nullable=True)
    duration_minutes = Column(Integer, nullable=False)
    price = Column(Integer, nullable=False) # Stored in cents or smallest currency unit

    owner = relationship("Owner", back_populates="services")
    bookings = relationship("Booking", back_populates="service")
    availabilities = relationship("Availability", back_populates="service") # Many-to-many relationship through association table

class Availability(Base):
    __tablename__ = "availabilities"
    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("owners.id"))
    service_id = Column(Integer, ForeignKey("services.id"), nullable=True) # Optional: availability can be for all services or specific
    
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    
    # For one-off availability: specific date
    date = Column(Date, nullable=True) 

    # For recurring availability: if `date` is NULL, then this is a recurring rule.
    recurrence_type = Column(Enum(RecurrenceType), default=RecurrenceType.NONE, nullable=False)
    # For WEEKLY: comma-separated list of weekdays (e.g., "MON,TUE,WED")
    # For MONTHLY: day of month (e.g., "15")
    recurrence_value = Column(String, nullable=True) # e.g., "MON,TUE,WED" or "15"
    recurrence_end_date = Column(Date, nullable=True) # When the recurring rule stops. If NULL, it's indefinite.

    owner = relationship("Owner", back_populates="availabilities")
    service = relationship("Service", back_populates="availabilities") # for specific service availability

class Booking(Base):
    __tablename__ = "bookings"
    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("owners.id"))
    service_id = Column(Integer, ForeignKey("services.id"))
    customer_name = Column(String, nullable=False)
    customer_email = Column(String, nullable=False)
    customer_phone = Column(String, nullable=True)
    date = Column(Date, nullable=False)
    time = Column(Time, nullable=False)
    status = Column(String, default="confirmed") # e.g., confirmed, cancelled
    created_at = Column(DateTime, server_default=func.now())

    owner = relationship("Owner", back_populates="bookings")
    service = relationship("Service", back_populates="bookings")