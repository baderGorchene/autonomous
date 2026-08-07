from sqlalchemy import Column, Integer, String, DateTime, Date, Time, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from .database import Base

class Owner(Base):
    __tablename__ = "owners"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    business_name = Column(String)
    slug = Column(String, unique=True, index=True)
    services_json = Column(String, default="[]") # Stores JSON array of service dicts
    availability_json = Column(String, default="{}") # Stores JSON dict of availability
    phone = Column(String, nullable=True)

    bookings = relationship("Booking", back_populates="owner")

class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    customer_name = Column(String, index=True)
    customer_email = Column(String, index=True)
    customer_phone = Column(String, nullable=True)
    booking_date = Column(Date)
    booking_time = Column(Time)
    service_name = Column(String) # Storing the name of the service booked
    owner_id = Column(Integer, ForeignKey("owners.id"))

    owner = relationship("Owner", back_populates="bookings")
