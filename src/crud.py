from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, and_
from datetime import date, time, datetime, timedelta
from typing import List, Optional

from . import models, schemas, security

# --- Owner CRUD ---
def get_owner(db: Session, owner_id: int):
    return db.query(models.Owner).filter(models.Owner.id == owner_id).first()

def get_owner_by_email(db: Session, email: str):
    return db.query(models.Owner).filter(models.Owner.email == email).first()

def get_owner_by_name(db: Session, name: str):
    return db.query(models.Owner).filter(func.lower(models.Owner.name) == func.lower(name)).first()

def get_all_owners(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.Owner).offset(skip).limit(limit).all()

def get_owner_by_stripe_customer_id(db: Session, stripe_customer_id: str):
    return db.query(models.Owner).filter(models.Owner.stripe_customer_id == stripe_customer_id).first()

def create_owner(db: Session, owner: schemas.OwnerCreate):
    hashed_password = security.get_password_hash(owner.password)
    db_owner = models.Owner(email=owner.email, hashed_password=hashed_password, name=owner.name, phone_number=owner.phone_number)
    db.add(db_owner)
    db.commit()
    db.refresh(db_owner)
    return db_owner

def update_owner(db: Session, owner_id: int, owner_update: schemas.OwnerUpdate):
    db_owner = get_owner(db, owner_id)
    if db_owner:
        update_data = owner_update.dict(exclude_unset=True)
        for key, value in update_data.items():
            setattr(db_owner, key, value)
        db.add(db_owner)
        db.commit()
        db.refresh(db_owner)
    return db_owner

def delete_owner(db: Session, owner_id: int):
    db_owner = get_owner(db, owner_id)
    if db_owner:
        db.delete(db_owner)
        db.commit()
    return db_owner

# --- Service CRUD ---
def get_service(db: Session, service_id: int, owner_id: int):
    return db.query(models.Service).filter(models.Service.id == service_id, models.Service.owner_id == owner_id).first()

def get_owner_services(db: Session, owner_id: int, skip: int = 0, limit: int = 100):
    return db.query(models.Service).filter(models.Service.owner_id == owner_id).offset(skip).limit(limit).all()

def create_owner_service(db: Session, service: schemas.ServiceCreate, owner_id: int):
    db_service = models.Service(**service.dict(), owner_id=owner_id)
    db.add(db_service)
    db.commit()
    db.refresh(db_service)
    return db_service

def update_service(db: Session, service_id: int, owner_id: int, service_update: schemas.ServiceUpdate):
    db_service = get_service(db, service_id, owner_id)
    if db_service:
        update_data = service_update.dict(exclude_unset=True)
        for key, value in update_data.items():
            setattr(db_service, key, value)
        db.add(db_service)
        db.commit()
        db.refresh(db_service)
    return db_service

def delete_service(db: Session, service_id: int, owner_id: int):
    db_service = get_service(db, service_id, owner_id)
    if db_service:
        db.delete(db_service)
        db.commit()
    return db_service

# --- Customer CRUD ---
def get_customer(db: Session, customer_id: int):
    return db.query(models.Customer).filter(models.Customer.id == customer_id).first()

def get_customer_by_email(db: Session, email: str):
    return db.query(models.Customer).filter(models.Customer.email == email).first()

def create_customer(db: Session, customer: schemas.CustomerCreate):
    db_customer = models.Customer(**customer.dict())
    db.add(db_customer)
    db.commit()
    db.refresh(db_customer)
    return db_customer

# --- Booking CRUD ---
def get_booking(db: Session, booking_id: int):
    return db.query(models.Booking).filter(models.Booking.id == booking_id).first()

def get_owner_upcoming_bookings(db: Session, owner_id: int):
    # Filter out past recurring bookings that are part of a series
    # Only show the *next* occurrence for recurring bookings, or individual bookings
    current_datetime = datetime.combine(date.today(), datetime.min.time())

    # Fetch individual bookings and the first occurrence of recurring bookings in the future
    bookings_query = db.query(models.Booking).options(joinedload(models.Booking.service), joinedload(models.Booking.customer)).filter(
        models.Booking.owner_id == owner_id,
        (models.Booking.date >= current_datetime.date())
    ).order_by(models.Booking.date, models.Booking.time)

    return bookings_query.all()

def get_owner_all_bookings(db: Session, owner_id: int):
    return db.query(models.Booking).options(joinedload(models.Booking.service), joinedload(models.Booking.customer)).filter(models.Booking.owner_id == owner_id).order_by(models.Booking.date.desc(), models.Booking.time.desc()).all()

def create_owner_booking(db: Session, booking: schemas.BookingCreate, owner_id: int, customer_id: Optional[int] = None):
    # If it's a recurring booking, generate a recurrence_id
    recurrence_id = str(uuid.uuid4()) if booking.is_recurring else None

    db_booking = models.Booking(
        **booking.dict(exclude_unset=True),
        owner_id=owner_id,
        customer_id=customer_id, # Link to customer account if provided
        recurrence_id=recurrence_id
    )
    db.add(db_booking)
    db.commit()
    db.refresh(db_booking)
    return db_booking

def update_booking(db: Session, booking_id: int, owner_id: int, booking_update: schemas.AdminBookingUpdate):
    db_booking = db.query(models.Booking).filter(models.Booking.id == booking_id, models.Booking.owner_id == owner_id).first()
    if db_booking:
        update_data = booking_update.dict(exclude_unset=True)
        for key, value in update_data.items():
            setattr(db_booking, key, value)
        db.add(db_booking)
        db.commit()
        db.refresh(db_booking)
    return db_booking

def delete_booking(db: Session, booking_id: int, owner_id: int):
    db_booking = db.query(models.Booking).filter(models.Booking.id == booking_id, models.Booking.owner_id == owner_id).first()
    if db_booking:
        db.delete(db_booking)
        db.commit()
    return db_booking

# --- Availability CRUD ---
def get_availability(db: Session, availability_id: int, owner_id: int):
    return db.query(models.Availability).filter(models.Availability.id == availability_id, models.Availability.owner_id == owner_id).first()

def get_owner_all_availabilities(db: Session, owner_id: int):
    return db.query(models.Availability).filter(models.Availability.owner_id == owner_id).order_by(models.Availability.date.desc(), models.Availability.start_time.asc()).all()

def create_owner_availability(db: Session, availability: schemas.AvailabilityCreate, owner_id: int):
    db_availability = models.Availability(**availability.dict(), owner_id=owner_id)
    db.add(db_availability)
    db.commit()
    db.refresh(db_availability)
    return db_availability

def delete_availability(db: Session, availability_id: int, owner_id: int):
    db_availability = get_availability(db, availability_id, owner_id)
    if db_availability:
        db.delete(db_availability)
        db.commit()
    return db_availability
