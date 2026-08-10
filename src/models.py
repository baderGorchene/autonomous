from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Boolean, Date, Time, Enum, Text, Float
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
import enum

Base = declarative_base()

class RecurrenceType(enum.Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"

class SubscriptionStatus(enum.Enum):
    ACTIVE = "active"
    CANCELED = "canceled"
    TRIALING = "trialing"
    PAST_DUE = "past_due"

class Owner(Base):
    __tablename__ = "owners"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    full_name = Column(String, nullable=True)
    phone_number = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    services = relationship("Service", back_populates="owner")
    bookings = relationship("Booking", back_populates="owner")
    availabilities = relationship("Availability", back_populates="owner")
    subscription = relationship("Subscription", uselist=False, back_populates="owner")
    reviews = relationship("Review", back_populates="owner")

class Service(Base):
    __tablename__ = "services"
    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("owners.id"))
    name = Column(String, index=True)
    description = Column(String, nullable=True)
    duration_minutes = Column(Integer)
    price = Column(Float)
    currency = Column(String, default="USD")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    owner = relationship("Owner", back_populates="services")
    bookings = relationship("Booking", back_populates="service")
    availabilities = relationship("Availability", back_populates="service")
    reviews = relationship("Review", back_populates="service")

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
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    owner = relationship("Owner", back_populates="availabilities")
    service = relationship("Service", back_populates="availabilities")

class Customer(Base):
    __tablename__ = "customers"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String, nullable=True)
    full_name = Column(String, nullable=True)
    phone_number = Column(String, nullable=True)
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
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    owner = relationship("Owner", back_populates="bookings")
    service = relationship("Service", back_populates="bookings")
    customer = relationship("Customer", back_populates="bookings")

class Subscription(Base):
    __tablename__ = "subscriptions"
    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("owners.id"), unique=True)
    stripe_customer_id = Column(String, unique=True, index=True)
    stripe_subscription_id = Column(String, unique=True, index=True)
    status = Column(Enum(SubscriptionStatus), default=SubscriptionStatus.TRIALING)
    current_period_end = Column(DateTime)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    owner = relationship("Owner", back_populates="subscription")

class Review(Base):
    __tablename__ = "reviews"
    id = Column(Integer, primary_key=True, index=True)
    service_id = Column(Integer, ForeignKey("services.id"))
    customer_id = Column(Integer, ForeignKey("customers.id"))
    owner_id = Column(Integer, ForeignKey("owners.id"))
    rating = Column(Integer, index=True)
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    service = relationship("Service", back_populates="reviews")
    customer = relationship("Customer", back_populates="reviews")
    owner = relationship("Owner", back_populates="reviews")