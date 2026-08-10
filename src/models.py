import enum
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, Enum, Float, Date, Time
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime, date

Base = declarative_base()

class RecurrenceType(enum.Enum):
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"

class SubscriptionStatus(enum.Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    CANCELLED = "CANCELLED"
    TRIAL = "TRIAL"

class Owner(Base):
    __tablename__ = "owners"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    is_active = Column(Boolean, default=True)
    name = Column(String, index=True)
    phone_number = Column(String, nullable=True)
    description = Column(String, nullable=True) # New field for SEO
    city = Column(String, nullable=True) # New field for SEO
    country = Column(String, nullable=True) # New field for SEO

    services = relationship("Service", back_populates="owner")
    bookings = relationship("Booking", back_populates="owner")
    availabilities = relationship("Availability", back_populates="owner")
    subscriptions = relationship("Subscription", back_populates="owner")

class Service(Base):
    __tablename__ = "services"
    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("owners.id"))
    name = Column(String, index=True)
    description = Column(String, nullable=True) # New field for SEO
    duration_minutes = Column(Integer)
    price = Column(Float)
    currency = Column(String, default="USD")
    slug = Column(String, unique=True, index=True)
    category = Column(String, nullable=True) # New field for SEO

    owner = relationship("Owner", back_populates="services")
    bookings = relationship("Booking", back_populates="service")
    availabilities = relationship("Availability", back_populates="service")
    reviews = relationship("Review", back_populates="service")

class Booking(Base):
    __tablename__ = "bookings"
    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("owners.id"))
    service_id = Column(Integer, ForeignKey("services.id"))
    customer_name = Column(String)
    customer_email = Column(String, index=True)
    customer_phone = Column(String, nullable=True)
    date = Column(Date, index=True)
    time = Column(Time)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_recurring = Column(Boolean, default=False)
    recurrence_end_date = Column(Date, nullable=True) # For recurring bookings

    owner = relationship("Owner", back_populates="bookings")
    service = relationship("Service", back_populates="bookings")

class Availability(Base):
    __tablename__ = "availabilities"
    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("owners.id"))
    service_id = Column(Integer, ForeignKey("services.id"), nullable=True) # Can be for a specific service or general
    date = Column(Date, nullable=True) # Specific date for one-off availability
    start_time = Column(Time)
    end_time = Column(Time)
    
    # Recurrence fields
    recurrence_type = Column(Enum(RecurrenceType), nullable=True) # DAILY, WEEKLY, MONTHLY
    recurrence_value = Column(String, nullable=True) # e.g., "MON,WED,FRI" for weekly, "15" for monthly
    recurrence_start_date = Column(Date, nullable=True)
    recurrence_end_date = Column(Date, nullable=True)

    owner = relationship("Owner", back_populates="availabilities")
    service = relationship("Service", back_populates="availabilities")

class Subscription(Base):
    __tablename__ = "subscriptions"
    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("owners.id"))
    stripe_customer_id = Column(String, index=True, unique=True)
    stripe_subscription_id = Column(String, index=True, unique=True)
    status = Column(Enum(SubscriptionStatus), default=SubscriptionStatus.TRIAL)
    current_period_end = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    owner = relationship("Owner", back_populates="subscriptions")

class Customer(Base):
    __tablename__ = "customers"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    name = Column(String)
    phone_number = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    reviews = relationship("Review", back_populates="customer")

class Review(Base):
    __tablename__ = "reviews"
    id = Column(Integer, primary_key=True, index=True)
    service_id = Column(Integer, ForeignKey("services.id"))
    customer_id = Column(Integer, ForeignKey("customers.id"))
    rating = Column(Integer) # 1-5 stars
    comment = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    service = relationship("Service", back_populates="reviews")
    customer = relationship("Customer", back_populates="reviews")
