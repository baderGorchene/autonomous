from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Float
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()

class Owner(Base):
    __tablename__ = "owners"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    business_name = Column(String)
    phone_number = Column(String, nullable=True)
    default_locale = Column(String, default="en")
    is_active = Column(Boolean, default=True)
    is_premium = Column(Boolean, default=False)
    stripe_customer_id = Column(String, nullable=True)
    stripe_subscription_id = Column(String, nullable=True)

    services = relationship("Service", back_populates="owner")
    bookings = relationship("Booking", back_populates="owner")

class Service(Base):
    __tablename__ = "services"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    description = Column(String, nullable=True)
    duration_minutes = Column(Integer)
    price = Column(Float)
    owner_id = Column(Integer, ForeignKey("owners.id"))
    is_active = Column(Boolean, default=True)

    owner = relationship("Owner", back_populates="services")
    bookings = relationship("Booking", back_populates="service")

class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    service_id = Column(Integer, ForeignKey("services.id"))
    owner_id = Column(Integer, ForeignKey("owners.id"))
    customer_name = Column(String)
    customer_email = Column(String)
    customer_phone = Column(String, nullable=True)
    start_time = Column(DateTime)
    end_time = Column(DateTime)
    status = Column(String, default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)
    recurrence_group_id = Column(String, nullable=True, index=True)

    service = relationship("Service", back_populates="bookings")
    owner = relationship("Owner", back_populates="bookings")

class Availability(Base):
    __tablename__ = "availability"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("owners.id"))
    day_of_week = Column(Integer)
    start_time = Column(String)
    end_time = Column(String)

    owner = relationship("Owner")
