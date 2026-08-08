from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()

class Owner(Base):
    __tablename__ = "owners"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    email = Column(String, unique=True, index=True)
    phone = Column(String, index=True, nullable=True)
    hashed_password = Column(String)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    subscription_status = Column(String, default="free") # free, premium, cancelled
    stripe_customer_id = Column(String, nullable=True)
    stripe_subscription_id = Column(String, nullable=True)
    is_admin = Column(Boolean, default=False) # New admin flag

    services = relationship("Service", back_populates="owner", cascade="all, delete-orphan")
    bookings = relationship("Booking", back_populates="owner", cascade="all, delete-orphan")

class Service(Base):
    __tablename__ = "services"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    description = Column(Text, nullable=True)
    duration_minutes = Column(Integer)
    price = Column(Integer) # Stored in cents or smallest currency unit
    owner_id = Column(Integer, ForeignKey("owners.id"))
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    owner = relationship("Owner", back_populates="services")
    bookings = relationship("Booking", back_populates="service", cascade="all, delete-orphan")

class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    customer_name = Column(String, index=True)
    customer_email = Column(String, index=True)
    customer_phone = Column(String, index=True, nullable=True)
    booking_time = Column(DateTime, index=True)
    status = Column(String, default="confirmed") # confirmed, cancelled, completed
    service_id = Column(Integer, ForeignKey("services.id"))
    owner_id = Column(Integer, ForeignKey("owners.id")) # Denormalized for easier querying
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    service = relationship("Service", back_populates="bookings")
    owner = relationship("Owner", back_populates="bookings")
