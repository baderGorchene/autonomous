from sqlalchemy import Column, Integer, String, DateTime, JSON, ForeignKey
from sqlalchemy.sql import func
from .database import Base

class Owner(Base):
    __tablename__ = 'owners'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    email = Column(String, unique=True, index=True)
    business_name = Column(String)
    slug = Column(String, unique=True, index=True)
    services_json = Column(JSON)
    availability_json = Column(JSON)
    created_at = Column(DateTime, server_default=func.now())

class Booking(Base):
    __tablename__ = 'bookings'
    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey('owners.id'))
    customer_name = Column(String)
    customer_email = Column(String)
    customer_phone = Column(String)
    service = Column(String)
    datetime = Column(DateTime)
    status = Column(String, default='pending')
    created_at = Column(DateTime, server_default=func.now())

class Settings(Base):
    __tablename__ = 'settings'
    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey('owners.id'))
    timezone = Column(String, default='UTC')
    language = Column(String, default='en')