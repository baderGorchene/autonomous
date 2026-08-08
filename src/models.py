from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, Date, Time, Text, Float
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import datetime

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
    stripe_customer_id = Column(String, nullable=True, unique=True)
    subscription_status = Column(String, default="free") # free, active, cancelled
    current_period_end = Column(DateTime, nullable=True)

    services = relationship("Service", back_populates="owner")
    bookings = relationship("Booking", back_populates="owner")
    availabilities = relationship("Availability", back_populates="owner")
    recurring_availabilities = relationship("RecurringAvailability", back_populates="owner")

class Service(Base):
    __tablename__ = "services"
    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("owners.id"))
    name = Column(String)
    description = Column(String)
    duration_minutes = Column(Integer)
    price = Column(Float, default=0.0)

    owner = relationship("Owner", back_populates="services")
    bookings = relationship("Booking", back_populates="service")
    recurring_availabilities = relationship("RecurringAvailability", back_populates="service")

class Booking(Base):
    __tablename__ = "bookings"
    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("owners.id"))
    service_id = Column(Integer, ForeignKey("services.id"))
    customer_name = Column(String)
    customer_email = Column(String)
    customer_phone = Column(String, nullable=True)
    booking_time = Column(DateTime)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    owner = relationship("Owner", back_populates="bookings")
    service = relationship("Service", back_populates="bookings")

class Availability(Base):
    __tablename__ = "availabilities"
    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("owners.id"))
    service_id = Column(Integer, ForeignKey("services.id"), nullable=True) # Can be general or service-specific
    date = Column(Date)
    start_time = Column(Time)
    end_time = Column(Time)
    is_available = Column(Boolean, default=True)

    owner = relationship("Owner", back_populates="availabilities")

class RecurringAvailability(Base):
    __tablename__ = "recurring_availabilities"
    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("owners.id"))
    service_id = Column(Integer, ForeignKey("services.id"), nullable=True)
    day_of_week = Column(Integer) # 0=Monday, 6=Sunday
    start_time = Column(Time)
    end_time = Column(Time)
    start_date = Column(Date, nullable=True) # When this rule becomes active
    end_date = Column(Date, nullable=True) # When this rule ceases to be active
    is_active = Column(Boolean, default=True)

    owner = relationship("Owner", back_populates="recurring_availabilities")
    service = relationship("Service", back_populates="recurring_availabilities")


class AdminUser(Base):
    __tablename__ = "admin_users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    is_active = Column(Boolean, default=True)
