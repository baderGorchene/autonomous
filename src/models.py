from sqlalchemy import Column, Integer, String, Date, Time, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from .database import Base

class Owner(Base):
    __tablename__ = "owners"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    business_name = Column(String)
    slug = Column(String, unique=True, index=True) # e.g., bookslot.app/their-name
    services_json = Column(String) # JSON string of services offered
    availability_json = Column(String) # JSON string of availability
    phone = Column(String, nullable=True) # Owner's phone number

    bookings = relationship("Booking", back_populates="owner")

class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("owners.id"))
    customer_name = Column(String)
    customer_email = Column(String)
    customer_phone = Column(String, nullable=True) # Customer's phone number
    booking_date = Column(Date)
    booking_time = Column(Time)
    service_name = Column(String) # Name of the service booked
    status = Column(String, default="confirmed") # e.g., confirmed, cancelled

    owner = relationship("Owner", back_populates="bookings")
