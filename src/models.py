from sqlalchemy import Column, Integer, String, Boolean, Date, Time, ForeignKey
from sqlalchemy.orm import relationship
from .database import Base

class Owner(Base):
    __tablename__ = "owners"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    business_name = Column(String)
    slug = Column(String, unique=True, index=True) # For public booking page URL
    phone = Column(String, nullable=True) # Owner's phone number
    is_active = Column(Boolean, default=True)
    services_json = Column(String, default="[]") # Stores list of services as JSON
    availability_json = Column(String, default="{}") # Stores availability as JSON
    
    bookings = relationship("Booking", back_populates="owner")

class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("owners.id"))
    customer_name = Column(String)
    customer_email = Column(String)
    customer_phone = Column(String, nullable=True)
    service_name = Column(String)
    booking_date = Column(Date)
    booking_time = Column(Time)
    notes = Column(String, nullable=True)

    owner = relationship("Owner", back_populates="bookings")
