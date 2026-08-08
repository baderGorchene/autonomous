from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from .database import Base
from datetime import datetime

class Owner(Base):
    __tablename__ = "owners"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    phone = Column(String, nullable=True)
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    subscription_status = Column(String, default="free") # "free", "premium"
    stripe_customer_id = Column(String, unique=True, index=True, nullable=True)
    stripe_subscription_id = Column(String, unique=True, index=True, nullable=True)

    services = relationship("Service", back_populates="owner")
    bookings = relationship("Booking", back_populates="owner")

class Service(Base):
    __tablename__ = "services"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("owners.id"))
    name = Column(String, index=True, nullable=False)
    description = Column(String, nullable=True)
    duration_minutes = Column(Integer, nullable=False)
    price = Column(Integer, nullable=False) # Price in smallest currency unit (e.g., cents)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    owner = relationship("Owner", back_populates="services")
    availability = relationship("Availability", back_populates="service")

class Availability(Base):
    __tablename__ = "availability"

    id = Column(Integer, primary_key=True, index=True)
    service_id = Column(Integer, ForeignKey("services.id"))
    day_of_week = Column(Integer, nullable=False) # 0=Monday, 6=Sunday
    start_time = Column(String, nullable=False) # "HH:MM"
    end_time = Column(String, nullable=False) # "HH:MM"
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    service = relationship("Service", back_populates="availability")

class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("owners.id"))
    service_id = Column(Integer, ForeignKey("services.id"))
    customer_name = Column(String, nullable=False)
    customer_email = Column(String, nullable=False)
    customer_phone = Column(String, nullable=True)
    booking_time = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    owner = relationship("Owner", back_populates="bookings")
    service = relationship("Service")

# Admin Model
class Admin(Base):
    __tablename__ = "admins"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    name = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
