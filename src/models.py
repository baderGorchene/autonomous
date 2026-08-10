from sqlalchemy import Column, Integer, String, Boolean, DateTime, Date, Time, ForeignKey, Text, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .database import Base
import datetime
import enum

class RecurrenceType(enum.Enum):
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"

class SubscriptionStatus(enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    TRIALING = "trialing"
    CANCELED = "canceled"

class Owner(Base):
    __tablename__ = "owners"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    name = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    locale = Column(String, default="en")
    
    stripe_customer_id = Column(String, unique=True, nullable=True)
    subscription_status = Column(Enum(SubscriptionStatus), default=SubscriptionStatus.INACTIVE)
    stripe_subscription_id = Column(String, unique=True, nullable=True)

    services = relationship("Service", back_populates="owner")
    availabilities = relationship("Availability", back_populates="owner")
    bookings = relationship("Booking", back_populates="owner")
    reviews = relationship("Review", back_populates="owner")

class Service(Base):
    __tablename__ = "services"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    description = Column(String, nullable=True)
    duration_minutes = Column(Integer)
    price = Column(Integer, default=0)
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
    
    recurrence_type = Column(Enum(RecurrenceType), nullable=True)
    recurrence_value = Column(String, nullable=True)
    recurrence_start_date = Column(Date, nullable=True)
    recurrence_end_date = Column(Date, nullable=True)

    owner = relationship("Owner", back_populates="availabilities")
    service = relationship("Service", back_populates="availabilities")

class Customer(Base):
    __tablename__ = "customers"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    phone = Column(String, nullable=True)
    name = Column(String, nullable=True)
    hashed_password = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

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
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    is_recurring = Column(Boolean, default=False)
    recurrence_id = Column(String, nullable=True)
    parent_booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=True)

    owner = relationship("Owner", back_populates="bookings")
    service = relationship("Service", back_populates="bookings")
    customer = relationship("Customer", back_populates="bookings")
    
    recurring_instances = relationship("Booking", backref="parent_booking", remote_side=[id])

class Review(Base):
    __tablename__ = "reviews"
    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("owners.id"))
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    customer_name = Column(String, nullable=True)
    rating = Column(Integer, index=True)
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    owner = relationship("Owner", back_populates="reviews")
    customer = relationship("Customer", back_populates="reviews")

class Subscription(Base):
    __tablename__ = "subscriptions"
    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("owners.id"), unique=True)
    stripe_subscription_id = Column(String, unique=True, index=True)
    stripe_customer_id = Column(String, index=True)
    status = Column(Enum(SubscriptionStatus), default=SubscriptionStatus.TRIALING)
    current_period_end = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())