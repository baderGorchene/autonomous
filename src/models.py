import enum
from datetime import date, time
from sqlalchemy import Column, Integer, String, Boolean, Date, Time, ForeignKey, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class RecurrenceType(str, enum.Enum):
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"

class Owner(Base):
    __tablename__ = "owners"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    phone_number = Column(String, nullable=True)
    address = Column(String, nullable=True)
    is_premium = Column(Boolean, default=False)

    services = relationship("Service", back_populates="owner")
    bookings = relationship("Booking", back_populates="owner")
    availabilities = relationship("Availability", back_populates="owner")

class Service(Base):
    __tablename__ = "services"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    description = Column(String, nullable=True)
    duration_minutes = Column(Integer)
    price = Column(Integer) # Stored in cents
    owner_id = Column(Integer, ForeignKey("owners.id"))

    owner = relationship("Owner", back_populates="services")
    bookings = relationship("Booking", back_populates="service")
    availabilities = relationship("Availability", back_populates="service")

class Booking(Base):
    __tablename__ = "bookings"
    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("owners.id"))
    service_id = Column(Integer, ForeignKey("services.id"))
    customer_name = Column(String)
    customer_email = Column(String)
    customer_phone = Column(String, nullable=True)
    date = Column(Date)
    time = Column(Time)
    recurrence_id = Column(Integer, nullable=True, index=True) # ID of the recurring series if applicable

    owner = relationship("Owner", back_populates="bookings")
    service = relationship("Service", back_populates="bookings")

class Availability(Base):
    __tablename__ = "availabilities"
    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("owners.id"))
    service_id = Column(Integer, ForeignKey("services.id"), nullable=True) # If None, applies to all services
    date = Column(Date, nullable=True) # Specific date for one-off availability
    start_time = Column(Time)
    end_time = Column(Time)
    recurrence_type = Column(Enum(RecurrenceType), nullable=True)
    recurrence_value = Column(String, nullable=True)
    recurrence_start_date = Column(Date, nullable=True)
    recurrence_end_date = Column(Date, nullable=True)

    owner = relationship("Owner", back_populates="availabilities")
    service = relationship("Service", back_populates="availabilities")
