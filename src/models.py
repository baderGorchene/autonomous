from sqlalchemy import Column, Integer, String, Text, Boolean
from sqlalchemy.orm import relationship
from .database import Base

class Owner(Base):
    __tablename__ = "owners"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    business_name = Column(String, index=True)
    slug = Column(String, unique=True, index=True)
    phone = Column(String, nullable=True)
    services_json = Column(Text) # Stores JSON string of services
    availability_json = Column(Text) # Stores JSON string of availability

    bookings = relationship("Booking", back_populates="owner")

class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, index=True)
    customer_name = Column(String)
    customer_email = Column(String)
    customer_phone = Column(String, nullable=True)
    service_name = Column(String)
    booking_date = Column(String)
    booking_time = Column(String)
    status = Column(String, default="pending")

    owner = relationship("Owner", back_populates="bookings")
