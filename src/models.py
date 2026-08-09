from sqlalchemy import Column, Integer, String, Date, Time, Boolean, ForeignKey, Enum, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from datetime import date, time, datetime
import enum

Base = declarative_base()

class RecurrenceType(str, enum.Enum):
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"

class Owner(Base):
    __tablename__ = "owners"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    full_name = Column(String)
    phone_number = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    stripe_customer_id = Column(String, nullable=True, index=True)
    subscription_status = Column(String, default="free")
    
    services = relationship("Service", back_populates="owner")
    bookings = relationship("Booking", back_populates="owner")
    availabilities = relationship("Availability", back_populates="owner")
    recurring_bookings = relationship("RecurringBooking", back_populates="owner")

class Service(Base):
    __tablename__ = "services"
    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("owners.id"))
    name = Column(String, index=True)
    description = Column(String, nullable=True)
    duration_minutes = Column(Integer, default=30)
    price = Column(Integer, default=0)
    currency = Column(String, default="USD")

    owner = relationship("Owner", back_populates="services")
    bookings = relationship("Booking", back_populates="service")
    availabilities = relationship("Availability", back_populates="service")
    recurring_bookings = relationship("RecurringBooking", back_populates="service")

class Availability(Base):
    __tablename__ = "availabilities"
    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("owners.id"))
    service_id = Column(Integer, ForeignKey("services.id"), nullable=True)
    date = Column(Date, nullable=True)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    
    recurrence_type = Column(Enum(RecurrenceType), nullable=True)
    recurrence_value = Column(String, nullable=True)
    recurrence_start_date = Column(Date, nullable=True)
    recurrence_end_date = Column(Date, nullable=True)

    owner = relationship("Owner", back_populates="availabilities")
    service = relationship("Service", back_populates="availabilities")

class Booking(Base):
    __tablename__ = "bookings"
    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("owners.id"))
    service_id = Column(Integer, ForeignKey("services.id"))
    customer_name = Column(String, index=True)
    customer_email = Column(String, index=True)
    customer_phone = Column(String, nullable=True)
    date = Column(Date, nullable=False)
    time = Column(Time, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    recurring_booking_id = Column(Integer, ForeignKey("recurring_bookings.id"), nullable=True)

    owner = relationship("Owner", back_populates="bookings")
    service = relationship("Service", back_populates="bookings")
    recurring_parent_booking = relationship("RecurringBooking", back_populates="bookings")

class RecurringBooking(Base):
    __tablename__ = "recurring_bookings"
    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("owners.id"))
    service_id = Column(Integer, ForeignKey("services.id"))
    customer_name = Column(String, index=True)
    customer_email = Column(String, index=True)
    customer_phone = Column(String, nullable=True)
    start_time = Column(Time, nullable=False)
    duration_minutes = Column(Integer, nullable=False, default=30)
    recurrence_type = Column(Enum(RecurrenceType), nullable=False)
    recurrence_value = Column(String, nullable=True)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    owner = relationship("Owner", back_populates="recurring_bookings")
    service = relationship("Service", back_populates="recurring_bookings")
    bookings = relationship("Booking", back_populates="recurring_parent_booking")
