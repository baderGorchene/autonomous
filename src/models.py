from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Date, Time
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from enum import Enum
from datetime import datetime

Base = declarative_base()

class RecurrenceType(str, Enum):
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
    services = relationship("Service", back_populates="owner")
    bookings = relationship("Booking", back_populates="owner")
    availabilities = relationship("Availability", back_populates="owner")
    subscriptions = relationship("Subscription", back_populates="owner")

class Service(Base):
    __tablename__ = "services"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    description = Column(String, nullable=True)
    duration_minutes = Column(Integer)
    price = Column(Integer)
    owner_id = Column(Integer, ForeignKey("owners.id"))
    owner = relationship("Owner", back_populates="services")
    bookings = relationship("Booking", back_populates="service")
    availabilities = relationship("Availability", back_populates="service")

class Customer(Base):
    __tablename__ = "customers"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    email = Column(String, index=True, nullable=True)
    phone = Column(String, index=True, nullable=True)
    hashed_password = Column(String, nullable=True)
    bookings = relationship("Booking", back_populates="customer")
    reviews = relationship("Review", back_populates="customer")

class Booking(Base):
    __tablename__ = "bookings"
    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("owners.id"))
    service_id = Column(Integer, ForeignKey("services.id"))
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    customer_name = Column(String)
    customer_email = Column(String)
    customer_phone = Column(String, nullable=True)
    date = Column(Date)
    time = Column(Time)
    is_confirmed = Column(Boolean, default=False)
    is_recurring = Column(Boolean, default=False)
    recurrence_id = Column(String, nullable=True)
    owner = relationship("Owner", back_populates="bookings")
    service = relationship("Service", back_populates="bookings")
    customer = relationship("Customer", back_populates="bookings")

class Availability(Base):
    __tablename__ = "availabilities"
    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("owners.id"))
    service_id = Column(Integer, ForeignKey("services.id"), nullable=True)
    date = Column(Date, nullable=True)
    start_time = Column(Time)
    end_time = Column(Time)
    recurrence_type = Column(String, nullable=True)
    recurrence_value = Column(String, nullable=True)
    recurrence_start_date = Column(Date, nullable=True)
    recurrence_end_date = Column(Date, nullable=True)
    owner = relationship("Owner", back_populates="availabilities")
    service = relationship("Service", back_populates="availabilities")

class Subscription(Base):
    __tablename__ = "subscriptions"
    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("owners.id"))
    stripe_customer_id = Column(String, unique=True, nullable=True)
    stripe_subscription_id = Column(String, unique=True, nullable=True)
    status = Column(String)
    current_period_end = Column(DateTime, nullable=True)
    owner = relationship("Owner", back_populates="subscriptions")

class Review(Base):
    __tablename__ = "reviews"
    id = Column(Integer, primary_key=True, index=True)
    service_id = Column(Integer, ForeignKey("services.id"))
    customer_id = Column(Integer, ForeignKey("customers.id"))
    rating = Column(Integer)
    comment = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    service = relationship("Service")
    customer = relationship("Customer", back_populates="reviews")