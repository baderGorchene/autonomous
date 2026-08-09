from sqlalchemy.orm import Session
from . import models, schemas
from datetime import date, time
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_password_hash(password):
    return pwd_context.hash(password)

# --- Owner CRUD ---
def get_owner(db: Session, owner_id: int):
    return db.query(models.Owner).filter(models.Owner.id == owner_id).first()

def get_owner_by_email(db: Session, email: str):
    return db.query(models.Owner).filter(models.Owner.email == email).first()

def get_owner_by_stripe_customer_id(db: Session, stripe_customer_id: str):
    return db.query(models.Owner).filter(models.Owner.stripe_customer_id == stripe_customer_id).first()

def create_owner(db: Session, owner: schemas.OwnerCreate):
    hashed_password = get_password_hash(owner.password)
    db_owner = models.Owner(
        email=owner.email,
        hashed_password=hashed_password,
        full_name=owner.full_name,
        phone_number=owner.phone_number
    )
    db.add(db_owner)
    db.commit()
    db.refresh(db_owner)
    return db_owner

def update_owner(db: Session, owner_id: int, full_name: str, phone_number: Optional[str] = None):
    db_owner = db.query(models.Owner).filter(models.Owner.id == owner_id).first()
    if db_owner:
        db_owner.full_name = full_name
        db_owner.phone_number = phone_number
        db.commit()
        db.refresh(db_owner)
    return db_owner

# --- Service CRUD ---
def get_service(db: Session, service_id: int):
    return db.query(models.Service).filter(models.Service.id == service_id).first()

def get_owner_services(db: Session, owner_id: int):
    return db.query(models.Service).filter(models.Service.owner_id == owner_id).all()

def create_owner_service(db: Session, service: schemas.ServiceCreate, owner_id: int):
    db_service = models.Service(**service.dict(), owner_id=owner_id)
    db.add(db_service)
    db.commit()
    db.refresh(db_service)
    return db_service

def delete_owner_service(db: Session, service_id: int, owner_id: int):
    db_service = db.query(models.Service).filter(
        models.Service.id == service_id, models.Service.owner_id == owner_id
    ).first()
    if db_service:
        db.delete(db_service)
        db.commit()
    return db_service

# --- Availability CRUD ---
def get_owner_availabilities(db: Session, owner_id: int):
    return db.query(models.Availability).filter(models.Availability.owner_id == owner_id).all()

def create_owner_availability(db: Session, availability: schemas.AvailabilityCreate, owner_id: int):
    db_availability = models.Availability(**availability.dict(), owner_id=owner_id)
    db.add(db_availability)
    db.commit()
    db.refresh(db_availability)
    return db_availability

def delete_owner_availability(db: Session, availability_id: int, owner_id: int):
    db_availability = db.query(models.Availability).filter(
        models.Availability.id == availability_id, models.Availability.owner_id == owner_id
    ).first()
    if db_availability:
        db.delete(db_availability)
        db.commit()
    return db_availability

# --- Booking CRUD ---
def get_booking(db: Session, booking_id: int):
    return db.query(models.Booking).filter(models.Booking.id == booking_id).first()

def get_owner_bookings(db: Session, owner_id: int):
    return db.query(models.Booking).filter(models.Booking.owner_id == owner_id).all()

def create_booking(db: Session, booking: schemas.BookingCreate, owner_id: int):
    db_booking = models.Booking(**booking.dict(), owner_id=owner_id)
    db.add(db_booking)
    db.commit()
    db.refresh(db_booking)
    return db_booking

def delete_booking(db: Session, booking_id: int, owner_id: int):
    db_booking = db.query(models.Booking).filter(
        models.Booking.id == booking_id, models.Booking.owner_id == owner_id
    ).first()
    if db_booking:
        db.delete(db_booking)
        db.commit()
    return db_booking

# --- Recurring Booking CRUD ---
def create_recurring_booking(db: Session, recurring_booking: schemas.RecurringBookingCreate, owner_id: int):
    db_recurring_booking = models.RecurringBooking(**recurring_booking.dict(), owner_id=owner_id)
    db.add(db_recurring_booking)
    db.commit()
    db.refresh(db_recurring_booking)
    return db_recurring_booking

def get_recurring_booking(db: Session, recurring_booking_id: int):
    return db.query(models.RecurringBooking).filter(models.RecurringBooking.id == recurring_booking_id).first()

def get_owner_recurring_bookings(db: Session, owner_id: int):
    return db.query(models.RecurringBooking).filter(models.RecurringBooking.owner_id == owner_id).all()
