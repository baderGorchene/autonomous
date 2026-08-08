import uuid
from datetime import datetime, date
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Date, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class Owner(Base):
    __tablename__ = "owners"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    name = Column(String)
    phone = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    services = relationship("Service", back_populates="owner")
    bookings = relationship("Booking", back_populates="owner")

class Service(Base):
    __tablename__ = "services"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_id = Column(String, ForeignKey("owners.id"))
    name = Column(String, index=True)
    description = Column(String, nullable=True)
    duration_minutes = Column(Integer)
    price = Column(Integer)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    owner = relationship("Owner", back_populates="services")
    bookings = relationship("Booking", back_populates="service")

class Booking(Base):
    __tablename__ = "bookings"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_id = Column(String, ForeignKey("owners.id"))
    service_id = Column(String, ForeignKey("services.id"))
    customer_name = Column(String)
    customer_email = Column(String)
    customer_phone = Column(String, nullable=True)
    booking_date = Column(Date)
    booking_time = Column(String) # e.g., "10:00"
    status = Column(String, default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)

    # New fields for recurring bookings
    is_recurring = Column(Boolean, default=False) # True if this booking is part of a series
    recurrence_pattern = Column(String, nullable=True) # e.g., "DAILY", "WEEKLY", "MONTHLY"
    recurrence_interval = Column(Integer, nullable=True) # e.g., 1 for every day/week, 2 for every other day/week
    recurrence_end_date = Column(Date, nullable=True) # Date when recurrence stops (for the whole series)
    
    # This field links child bookings to their original/parent booking in a recurring series.
    # If this booking *is* the original/parent booking, this field will be NULL.
    # If this booking is a *child* in a recurring series, this field will point to the ID of the original booking.
    recurring_original_id = Column(String, ForeignKey("bookings.id"), nullable=True) 

    # Relationship for the original booking (parent) to its series (children)
    # The 'original_booking' relationship allows a child booking to access its parent.
    # The 'recurring_series_bookings' relationship allows a parent booking to access its children.
    original_booking = relationship(
        "Booking",
        remote_side=[id], # The 'id' on the remote side (the parent)
        back_populates="recurring_series_bookings",
        foreign_keys=[recurring_original_id]
    )
    
    recurring_series_bookings = relationship(
        "Booking",
        back_populates="original_booking",
        foreign_keys=[id] # The 'id' on the local side (the parent)
    )

    owner = relationship("Owner", back_populates="bookings")
    service = relationship("Service", back_populates="bookings")
