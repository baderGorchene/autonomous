from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Date, Time, Enum, Float
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from enum import Enum as PyEnum
import datetime

Base = declarative_base()

class RecurrenceType(PyEnum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    NONE = "none" # For one-off availability

class Owner(Base):
    __tablename__ = "owners"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    name = Column(String)
    phone_number = Column(String, nullable=True)
    locale = Column(String, default="en")
    is_premium = Column(Boolean, default=False)
    stripe_customer_id = Column(String, nullable=True)
    stripe_subscription_id = Column(String, nullable=True)

    services = relationship("Service", back_populates="owner")
    availabilities = relationship("Availability", back_populates="owner")
    bookings = relationship("Booking", back_populates="owner")
    customers = relationship("Customer", back_populates="owner") # New relationship

class Service(Base):
    __tablename__ = "services"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    description = Column(String, nullable=True)
    duration_minutes = Column(Integer)
    price = Column(Float)
    owner_id = Column(Integer, ForeignKey("owners.id"))

    owner = relationship("Owner", back_populates="services")
    availabilities = relationship("Availability", back_populates="service")
    bookings = relationship("Booking", back_populates="service")

class Availability(Base):
    __tablename__ = "availabilities"
    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("owners.id"))
    service_id = Column(Integer, ForeignKey("services.id"), nullable=True)
    date = Column(Date, nullable=True)
    start_time = Column(Time)
    end_time = Column(Time)
    recurrence_type = Column(Enum(RecurrenceType), default=RecurrenceType.NONE)
    recurrence_value = Column(String, nullable=True)
    recurrence_start_date = Column(Date, nullable=True)
    recurrence_end_date = Column(Date, nullable=True)

    owner = relationship("Owner", back_populates="availabilities")
    service = relationship("Service", back_populates="availabilities")

class Customer(Base): # New Customer Model
    __tablename__ = "customers"
    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("owners.id")) # Customer belongs to an owner
    name = Column(String)
    email = Column(String, index=True, nullable=True)
    phone_number = Column(String, index=True, nullable=True)

    owner = relationship("Owner", back_populates="customers")
    bookings = relationship("Booking", back_populates="customer")

class Booking(Base):
    __tablename__ = "bookings"
    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("owners.id"))
    service_id = Column(Integer, ForeignKey("services.id"))
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True) # New: Link to Customer
    date = Column(Date)
    time = Column(Time)
    is_confirmed = Column(Boolean, default=False)
    recurrence_id = Column(String, nullable=True)

    owner = relationship("Owner", back_populates="bookings")
    service = relationship("Service", back_populates="bookings")
    customer = relationship("Customer", back_populates="bookings") # New: Relationship to Customer
