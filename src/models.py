from sqlalchemy import Column, Integer, String, ForeignKey, Boolean, Date, Time, Enum, Text
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import UniqueConstraint
from datetime import date, time
import enum

Base = declarative_base()

class BookingStatus(enum.Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELED = "canceled"
    COMPLETED = "completed"

class RecurrenceType(enum.Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"

class Owner(Base):
    __tablename__ = "owners"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    name = Column(String, nullable=True)
    phone_number = Column(String, nullable=True) # Owner's phone number for notifications
    is_active = Column(Boolean, default=True)
    bookings_count = Column(Integer, default=0) # For analytics/monetization
    stripe_customer_id = Column(String, nullable=True) # For Stripe subscriptions
    subscription_status = Column(String, default="free") # 'free', 'premium', 'canceled'

    services = relationship("Service", back_populates="owner")
    availabilities = relationship("Availability", back_populates="owner")
    bookings = relationship("Booking", back_populates="owner")
    customers = relationship("Customer", back_populates="owner") # New: Relationship to customers

class Service(Base):
    __tablename__ = "services"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    description = Column(String, nullable=True)
    duration_minutes = Column(Integer)
    price = Column(Integer, default=0) # Price in cents
    owner_id = Column(Integer, ForeignKey("owners.id"))

    owner = relationship("Owner", back_populates="services")
    bookings = relationship("Booking", back_populates="service")
    availabilities = relationship("Availability", back_populates="service")

class Availability(Base):
    __tablename__ = "availabilities"
    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("owners.id"))
    service_id = Column(Integer, ForeignKey("services.id"), nullable=True) # Can be for all services (None) or specific
    date = Column(Date, nullable=True) # For one-off availability
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    recurrence_type = Column(Enum(RecurrenceType), nullable=True) # e.g., DAILY, WEEKLY, MONTHLY
    recurrence_value = Column(String, nullable=True) # e.g., "MON,WED,FRI" for weekly, "15" for monthly
    recurrence_start_date = Column(Date, nullable=True)
    recurrence_end_date = Column(Date, nullable=True)

    owner = relationship("Owner", back_populates="availabilities")
    service = relationship("Service", back_populates="availabilities")

class Customer(Base):
    __tablename__ = "customers"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, index=True, nullable=False)
    hashed_password = Column(String, nullable=True) # Optional for account creation
    name = Column(String, nullable=True)
    phone_number = Column(String, nullable=True)
    owner_id = Column(Integer, ForeignKey("owners.id"), nullable=False)

    owner = relationship("Owner", back_populates="customers")
    bookings = relationship("Booking", back_populates="customer")

    __table_args__ = (
        UniqueConstraint('email', 'owner_id', name='_customer_email_owner_uc'),
    )

class Booking(Base):
    __tablename__ = "bookings"
    id = Column(Integer, primary_key=True, index=True)
    service_id = Column(Integer, ForeignKey("services.id"), nullable=False)
    owner_id = Column(Integer, ForeignKey("owners.id"), nullable=False)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True) # New: Optional customer account
    date = Column(Date, nullable=False)
    time = Column(Time, nullable=False)
    customer_name = Column(String, nullable=False)
    customer_email = Column(String, nullable=False)
    customer_phone = Column(String, nullable=True)
    status = Column(Enum(BookingStatus), default=BookingStatus.PENDING)
    is_recurring = Column(Boolean, default=False)
    recurrence_id = Column(String, nullable=True, index=True) # To group recurring bookings

    service = relationship("Service", back_populates="bookings")
    owner = relationship("Owner", back_populates="bookings")
    customer = relationship("Customer", back_populates="bookings") # New relationship

class Payment(Base):
    __tablename__ = "payments"
    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("owners.id"), nullable=False)
    stripe_charge_id = Column(String, unique=True, nullable=False)
    amount = Column(Integer, nullable=False) # In cents
    currency = Column(String, nullable=False)
    status = Column(String, nullable=False) # e.g., 'succeeded', 'failed'
    created_at = Column(Date, default=date.today)

    owner = relationship("Owner")
