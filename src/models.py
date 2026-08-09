from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Time, Date, DateTime, Float
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime, date, time
from typing import Optional, List

Base = declarative_base()

class Owner(Base):
    __tablename__ = "owners"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    company_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    services: Mapped[List["Service"]] = relationship("Service", back_populates="owner", cascade="all, delete-orphan")
    bookings: Mapped[List["Booking"]] = relationship("Booking", back_populates="owner", cascade="all, delete-orphan")
    availabilities: Mapped[List["Availability"]] = relationship("Availability", back_populates="owner", cascade="all, delete-orphan")

class Service(Base):
    __tablename__ = "services"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("owners.id"))
    name: Mapped[str] = mapped_column(String, index=True)
    description: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    duration_minutes: Mapped[int] = mapped_column(Integer, default=30) # Added duration
    price: Mapped[float] = mapped_column(Float, default=0.0)

    owner: Mapped["Owner"] = relationship("Owner", back_populates="services")
    availabilities: Mapped[List["Availability"]] = relationship("Availability", back_populates="service", cascade="all, delete-orphan")
    bookings: Mapped[List["Booking"]] = relationship("Booking", back_populates="service", cascade="all, delete-orphan")

class Availability(Base):
    __tablename__ = "availabilities"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("owners.id"))
    service_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("services.id"), nullable=True)
    
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)
    
    start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=False)
    recurrence_type: Mapped[Optional[str]] = mapped_column(String, nullable=True) # e.g., "daily", "weekly", "monthly"
    recurrence_details: Mapped[Optional[str]] = mapped_column(String, nullable=True) # JSON string: {"days_of_week": [0,1,2]} for weekly, {"day_of_month": 15} for monthly

    owner: Mapped["Owner"] = relationship("Owner", back_populates="availabilities")
    service: Mapped[Optional["Service"]] = relationship("Service", back_populates="availabilities")

class Booking(Base):
    __tablename__ = "bookings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    service_id: Mapped[int] = mapped_column(Integer, ForeignKey("services.id"))
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("owners.id"))
    customer_name: Mapped[str] = mapped_column(String, index=True)
    customer_email: Mapped[str] = mapped_column(String, index=True)
    customer_phone: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    start_time: Mapped[datetime] = mapped_column(DateTime)
    end_time: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String, default="pending")

    service: Mapped["Service"] = relationship("Service", back_populates="bookings")
    owner: Mapped["Owner"] = relationship("Owner", back_populates="bookings")
