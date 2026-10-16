from sqlalchemy.orm import Session
from datetime import datetime, date, timedelta
from typing import List, Optional
from fastapi import HTTPException, status
import uuid

from . import models, schemas
from .security import get_password_hash, verify_password

# --- Owner CRUD ---
def get_owner(db: Session, owner_id: int) -> Optional[models.Owner]:
    return db.query(models.Owner).filter(models.Owner.id == owner_id).first()

def get_owner_by_email(db: Session, email: str) -> Optional[models.Owner]:
    return db.query(models.Owner).filter(models.Owner.email == email).first()

def get_owner_by_slug(db: Session, slug: str) -> Optional[models.Owner]:
    return db.query(models.Owner).filter(models.Owner.slug == slug).first()

def get_owner_by_username(db: Session, username: str) -> Optional[models.Owner]:
    owner = db.query(models.Owner).filter(models.Owner.slug == username).first()
    if not owner:
        owner = db.query(models.Owner).filter(models.Owner.email == username).first()
    return owner

def create_owner(db: Session, owner: schemas.OwnerCreate) -> models.Owner:
    pwd = getattr(owner, "password", None) or "password123"
    hashed_pwd = get_password_hash(pwd)
    slug = getattr(owner, "slug", None)
    name = getattr(owner, "name", "")
    if not slug:
        import re
        slug = re.sub(r'[^a-zA-Z0-9]+', '-', name.lower()).strip('-') or "owner"

    db_owner = models.Owner(
        email=owner.email,
        hashed_password=hashed_pwd,
        name=owner.name,
        business_name=getattr(owner, "business_name", None) or owner.name,
        slug=slug,
        phone=getattr(owner, "phone", None),
        is_active=True
    )
    db.add(db_owner)
    db.commit()
    db.refresh(db_owner)
    return db_owner

def authenticate_owner(db: Session, email: str, password: str):
    owner = get_owner_by_email(db, email=email)
    if not owner:
        return False
    if not verify_password(password, owner.hashed_password):
        return False
    return owner

def update_owner(db: Session, owner_id: int, owner_update: schemas.OwnerUpdate):
    db_owner = get_owner(db, owner_id)
    if not db_owner:
        return None
    update_data = owner_update.model_dump(exclude_unset=True) if hasattr(owner_update, "model_dump") else owner_update.dict(exclude_unset=True)
    for key, value in update_data.items():
        if hasattr(db_owner, key):
            setattr(db_owner, key, value)
    db.add(db_owner)
    db.commit()
    db.refresh(db_owner)
    return db_owner

def update_owner_profile(db: Session, owner: models.Owner, update_data):
    data = update_data.model_dump(exclude_unset=True) if hasattr(update_data, "model_dump") else update_data.dict(exclude_unset=True)
    for key, value in data.items():
        if hasattr(owner, key):
            setattr(owner, key, value)
    db.add(owner)
    db.commit()
    db.refresh(owner)
    return owner

def get_owners(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.Owner).offset(skip).limit(limit).all()

def get_all_owners(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.Owner).offset(skip).limit(limit).all()

def delete_owner(db: Session, owner_id: int):
    db_owner = get_owner(db, owner_id)
    if db_owner:
        db.delete(db_owner)
        db.commit()
        return True
    return False

# --- Service CRUD ---
def get_service(db: Session, service_id: int):
    return db.query(models.Service).filter(models.Service.id == service_id).first()

def get_owner_services(db: Session, owner_id: int):
    return db.query(models.Service).filter(models.Service.owner_id == owner_id).all()

def create_owner_service(db: Session, service: schemas.ServiceCreate, owner_id: int):
    data = service.model_dump() if hasattr(service, "model_dump") else service.dict()
    db_service = models.Service(**data, owner_id=owner_id)
    db.add(db_service)
    db.commit()
    db.refresh(db_service)
    return db_service

# --- Availability CRUD ---
def create_owner_availability(db: Session, availability: schemas.AvailabilityCreate, owner_id: int):
    data = availability.model_dump() if hasattr(availability, "model_dump") else availability.dict()
    db_avail = models.Availability(**data, owner_id=owner_id)
    db.add(db_avail)
    db.commit()
    db.refresh(db_avail)
    return db_avail

def get_owner_availabilities(db: Session, owner_id: int):
    return db.query(models.Availability).filter(models.Availability.owner_id == owner_id).all()

# --- Customer CRUD ---
def get_customer(db: Session, customer_id: int):
    return db.query(models.Customer).filter(models.Customer.id == customer_id).first()

def get_customer_by_email(db: Session, email: str):
    return db.query(models.Customer).filter(models.Customer.email == email).first()

def create_customer(db: Session, customer: schemas.CustomerCreate):
    data = customer.model_dump() if hasattr(customer, "model_dump") else customer.dict()
    db_cust = models.Customer(**data)
    db.add(db_cust)
    db.commit()
    db.refresh(db_cust)
    return db_cust

# --- Booking CRUD ---
def get_booking(db: Session, booking_id: int):
    return db.query(models.Booking).filter(models.Booking.id == booking_id).first()

def get_upcoming_owner_bookings(db: Session, owner_id: int):
    today = date.today()
    return db.query(models.Booking).filter(
        models.Booking.owner_id == owner_id,
        models.Booking.date >= today
    ).order_by(models.Booking.date, models.Booking.time).all()

def create_booking(db: Session, booking: schemas.BookingCreate, owner_id: Optional[int] = None):
    data = booking.model_dump() if hasattr(booking, "model_dump") else booking.dict()
    target_owner_id = owner_id or data.get("owner_id")
    filtered = {k: v for k, v in data.items() if hasattr(models.Booking, k)}
    if data.get("booking_time"):
        bt = data["booking_time"]
        if hasattr(bt, "date") and not filtered.get("date"):
            filtered["date"] = bt.date()
        if hasattr(bt, "time") and not filtered.get("time"):
            filtered["time"] = bt.time()
    if target_owner_id:
        filtered["owner_id"] = target_owner_id
    if not filtered.get("service_name") and filtered.get("service_id"):
        svc = get_service(db, filtered["service_id"])
        if svc:
            filtered["service_name"] = svc.name
    filtered.setdefault("status", "pending")
    db_booking = models.Booking(**filtered)
    if target_owner_id:
        db_booking.owner_id = target_owner_id
    db.add(db_booking)
    db.commit()
    db.refresh(db_booking)
    return db_booking


def create_recurring_booking(db: Session, recurring_booking: schemas.RecurringBookingCreate):
    data = recurring_booking.model_dump() if hasattr(recurring_booking, "model_dump") else recurring_booking.dict()
    filtered = {k: v for k, v in data.items() if hasattr(models.Booking, k)}
    filtered["is_recurring"] = True
    filtered["recurrence_id"] = str(uuid.uuid4())
    db_booking = models.Booking(**filtered)
    db.add(db_booking)
    db.commit()
    db.refresh(db_booking)
    return [db_booking]

def update_owner_subscription(db: Session, owner_id: int, stripe_customer_id: str, stripe_subscription_id: str):
    owner = get_owner(db, owner_id)
    if owner:
        if hasattr(owner, "stripe_customer_id"):
            owner.stripe_customer_id = stripe_customer_id
        if hasattr(owner, "stripe_subscription_id"):
            owner.stripe_subscription_id = stripe_subscription_id
        owner.is_premium = True
        db.commit()
        db.refresh(owner)
    return owner