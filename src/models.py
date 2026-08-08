from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
import uuid

from src.database import Base

class Owner(Base):
    __tablename__ = "owners"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    name = Column(String)
    phone = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    stripe_customer_id = Column(String, nullable=True)
    subscription_status = Column(String, default="inactive")

    services = relationship("Service", back_populates="owner")
    availabilities = relationship("Availability", back_populates="owner")
    bookings = relationship("Booking", back_populates="owner")

class Service(Base):
    __tablename__ = "services"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("owners.id"))
    name = Column(String, index=True)
    description = Column(String, nullable=True)
    duration_minutes = Column(Integer)
    price = Column(Integer)
    is_active = Column(Boolean, default=True)

    owner = relationship("Owner", back_populates="services")
    bookings = relationship("Booking", back_populates="service")

class Availability(Base):
    __tablename__ = "availabilities"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("owners.id"))
    day_of_week = Column(Integer)
    start_time = Column(String)
    end_time = Column(String)

    owner = relationship("Owner", back_populates="availabilities")

class Booking(Base):
    __tablename__ = "bookings"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("owners.id"))
    service_id = Column(UUID(as_uuid=True), ForeignKey("services.id"))
    customer_name = Column(String)
    customer_email = Column(String)
    customer_phone = Column(String, nullable=True)
    start_time = Column(DateTime)
    end_time = Column(DateTime)
    status = Column(String, default="confirmed")
    created_at = Column(DateTime, default=datetime.utcnow)

    is_recurring = Column(Boolean, default=False)
    recurrence_pattern = Column(String, nullable=True)
    recurrence_end_date = Column(DateTime, nullable=True)
    recurrence_count = Column(Integer, nullable=True)
    recurrence_group_id = Column(UUID(as_uuid=True), nullable=True)

    owner = relationship("Owner", back_populates="bookings")
    service = relationship("Service", back_populates="bookings")
