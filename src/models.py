from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()

class Owner(Base):
    __tablename__ = "owners"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    full_name = Column(String)
    phone_number = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    stripe_customer_id = Column(String, unique=True, nullable=True)
    is_premium = Column(Boolean, default=False)

class Service(Base):
    __tablename__ = "services"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, index=True)
    name = Column(String)
    description = Column(Text, nullable=True)
    duration_minutes = Column(Integer)
    price = Column(Integer) # Stored in cents
    is_active = Column(Boolean, default=True)

class Availability(Base):
    __tablename__ = "availability"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, index=True)
    day_of_week = Column(Integer) # 0=Monday, 6=Sunday
    start_time = Column(String) # e.g., "09:00"
    end_time = Column(String) # e.g., "17:00"

class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, index=True)
    service_id = Column(Integer, index=True)
    customer_name = Column(String)
    customer_email = Column(String)
    customer_phone = Column(String, nullable=True)
    booking_date = Column(DateTime)
    start_time = Column(String)
    end_time = Column(String)
    status = Column(String, default="confirmed")
    created_at = Column(DateTime, default=datetime.utcnow)
