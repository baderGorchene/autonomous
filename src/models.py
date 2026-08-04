from sqlalchemy import Column, Integer, String, DateTime, Date, Time, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from .database import Base
from datetime import datetime, date, time

class Owner(Base):
    __tablename__ = "owners"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    business_name = Column(String)
    slug = Column(String, unique=True, index=True) # For public booking page URL
    services_json = Column(String, default="[]") # JSON string of services
    availability_json = Column(String, default="{}") # JSON string of availability
    phone = Column(String, nullable=True) # Owner's phone number

    bookings = relationship("Booking", back_populates="owner")

class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("owners.id"))
    customer_name = Column(String, index=True)
    customer_email = Column(String, index=True)
    customer_phone = Column(String, nullable=True) # Customer's phone number
    service_name = Column(String)
    booking_date = Column(Date, default=date.today)
    booking_time = Column(Time, default=time(9, 0)) # Default to 9 AM
    created_at = Column(DateTime, default=datetime.now)

    owner = relationship("Owner", back_populates="bookings")
