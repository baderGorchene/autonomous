from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from .database import Base
import datetime

class Owner(Base):
    __tablename__ = "owners"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    business_name = Column(String)
    slug = Column(String, unique=True, index=True)
    phone = Column(String, nullable=True)
    services_json = Column(Text, default="[]")
    availability_json = Column(Text, default="{}")

    bookings = relationship("Booking", back_populates="owner")

class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("owners.id"))
    customer_name = Column(String)
    customer_email = Column(String)
    customer_phone = Column(String, nullable=True)
    service_name = Column(String)
    booking_time = Column(DateTime)
    status = Column(String, default="confirmed")

    owner = relationship("Owner", back_populates="bookings")
