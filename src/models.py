from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, ForeignKey, Date, Time, Text
from sqlalchemy.orm import declarative_base, sessionmaker, relationship, Mapped, mapped_column
from datetime import datetime, date, time
import json

Base = declarative_base()

class Owner(Base):
    __tablename__ = "owners"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    name: Mapped[str] = mapped_column(String)
    phone: Mapped[str] = mapped_column(String, nullable=True)
    profile_picture_url: Mapped[str] = mapped_column(String, nullable=True)
    booking_page_slug: Mapped[str] = mapped_column(String, unique=True, index=True)
    currency: Mapped[str] = mapped_column(String, default="USD")
    locale: Mapped[str] = mapped_column(String, default="en")

    # Stripe subscription fields
    stripe_customer_id: Mapped[str] = mapped_column(String, nullable=True, index=True)
    stripe_subscription_id: Mapped[str] = mapped_column(String, nullable=True, index=True)
    subscription_status: Mapped[str] = mapped_column(String, default="free") # free, active, cancelled, past_due

    services: Mapped[list["Service"]] = relationship(back_populates="owner", cascade="all, delete-orphan")
    availabilities: Mapped[list["Availability"]] = relationship(back_populates="owner", cascade="all, delete-orphan") # Changed to AvailabilityRule
    bookings: Mapped[list["Booking"]] = relationship(back_populates="owner", cascade="all, delete-orphan")

class Service(Base):
    __tablename__ = "services"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("owners.id"))
    name: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(String, nullable=True)
    duration_minutes: Mapped[int] = mapped_column(Integer)
    price: Mapped[float] = mapped_column(Integer) # Storing as integer (cents) is better for currency
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    owner: Mapped["Owner"] = relationship(back_populates="services")
    bookings: Mapped[list["Booking"]] = relationship(back_populates="service", cascade="all, delete-orphan")

# Refactored Availability to store recurrence rules and patterns
class Availability(Base):
    __tablename__ = "availabilities"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("owners.id"))
    
    # Daily time range for the rule
    start_time_of_day: Mapped[time] = mapped_column(Time(timezone=False)) # e.g., 09:00:00
    end_time_of_day: Mapped[time] = mapped_column(Time(timezone=False))   # e.g., 17:00:00

    # Recurrence rule string (iCalendar RRULE format, e.g., "FREQ=WEEKLY;BYDAY=MO,WE,FR")
    rrule_string: Mapped[str] = mapped_column(String, nullable=True)
    
    # Period for which this rule is active
    start_date: Mapped[date] = mapped_column(Date) # When the pattern begins
    end_date: Mapped[date] = mapped_column(Date, nullable=True) # When the pattern ends (optional)
    
    # Exceptions: dates when the rule does NOT apply (JSON string of YYYY-MM-DD dates)
    exception_dates_json: Mapped[str] = mapped_column(String, default="[]") 

    owner: Mapped["Owner"] = relationship(back_populates="availabilities")
    
    @property
    def exception_dates(self) -> list[date]:
        return [date.fromisoformat(d) for d in json.loads(self.exception_dates_json)]

    @exception_dates.setter
    def exception_dates(self, dates: list[date]):
        self.exception_dates_json = json.dumps([d.isoformat() for d in dates])

class Booking(Base):
    __tablename__ = "bookings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("owners.id"))
    service_id: Mapped[int] = mapped_column(Integer, ForeignKey("services.id"))
    customer_name: Mapped[str] = mapped_column(String)
    customer_email: Mapped[str] = mapped_column(String)
    customer_phone: Mapped[str] = mapped_column(String, nullable=True)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String, default="confirmed") # confirmed, cancelled, completed

    owner: Mapped["Owner"] = relationship(back_populates="bookings")
    service: Mapped["Service"] = relationship(back_populates="bookings")
