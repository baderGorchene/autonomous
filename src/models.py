from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from .database import Base
from datetime import datetime

class Owner(Base):
    __tablename__ = "owners"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    business_name = Column(String)
    slug = Column(String, unique=True, index=True)
    services_json = Column(Text, default="[]")
    availability_json = Column(Text, default="{}")
    phone = Column(String, nullable=True)

    bookings = relationship("Booking", back_populates="owner")

class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("owners.id"))
    customer_name = Column(String, index=True)
    customer_email = Column(String)
    customer_phone = Column(String, nullable=True)
    service_name = Column(String)
    booking_time = Column(DateTime, default=datetime.utcnow)
    status = Column(String, default="pending")

    owner = relationship("Owner", back_populates="bookings")
