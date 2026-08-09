from sqlalchemy import Column, Integer, String, ForeignKey, Time, Date, Float, Boolean, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from datetime import date, time, datetime

Base = declarative_base()

class Owner(Base):
    __tablename__ = "owners"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    is_active = Column(Boolean, default=True)
    phone = Column(String, nullable=True)

    services = relationship("Service", back_populates="owner")
    availabilities = relationship("OwnerAvailability", back_populates="owner")
    bookings = relationship("Booking", back_populates="owner")

class Service(Base):
    __tablename__ = "services"
    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("owners.id"))
    name = Column(String, index=True)
    description = Column(String, nullable=True)
    duration_minutes = Column(Integer)
    price = Column(Float)
    currency = Column(String)

    owner = relationship("Owner", back_populates="services")
    bookings = relationship("Booking", back_populates="service")

class OwnerAvailability(Base):
    __tablename__ = "owner_availability"
    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("owners.id"))
    day_of_week = Column(Integer, nullable=True) # 0=Monday, 6=Sunday. For weekly recurrence.
    start_time = Column(Time)
    end_time = Column(Time)
    start_date = Column(Date, nullable=True) # When this availability rule starts to apply (inclusive)
    end_date = Column(Date, nullable=True) # When this availability rule stops applying (inclusive)
    recurrence_type = Column(String, default="one_off") # "one_off", "daily", "weekly"

    owner = relationship("Owner", back_populates="availabilities")

class Booking(Base):
    __tablename__ = "bookings"
    id = Column(Integer, primary_key=True, index=True)
    service_id = Column(Integer, ForeignKey("services.id"))
    owner_id = Column(Integer, ForeignKey("owners.id"))
    customer_name = Column(String)
    customer_email = Column(String)
    customer_phone = Column(String, nullable=True)
    booking_time = Column(DateTime)
    status = Column(String, default="confirmed")

    service = relationship("Service", back_populates="bookings")
    owner = relationship("Owner", back_populates="bookings")
