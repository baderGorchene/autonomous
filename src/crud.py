from sqlalchemy.orm import Session
from . import models, schemas
from datetime import datetime, timedelta
from sqlalchemy import func

def get_owner_by_email(db: Session, email: str):
    return db.query(models.Owner).filter(models.Owner.email == email).first()

def create_owner(db: Session, owner: schemas.OwnerCreate, hashed_password: str):
    db_owner = models.Owner(email=owner.email, hashed_password=hashed_password, name=owner.name, phone=owner.phone)
    db.add(db_owner)
    db.commit()
    db.refresh(db_owner)
    return db_owner

def get_owner(db: Session, owner_id: int):
    return db.query(models.Owner).filter(models.Owner.id == owner_id).first()

def get_owner_services(db: Session, owner_id: int):
    return db.query(models.Service).filter(models.Service.owner_id == owner_id).all()

def get_service_by_id(db: Session, service_id: int):
    return db.query(models.Service).filter(models.Service.id == service_id).first()

def create_booking(db: Session, booking: schemas.BookingCreate, owner_id: int):
    db_booking = models.Booking(**booking.model_dump(), owner_id=owner_id)
    db.add(db_booking)
    db.commit()
    db.refresh(db_booking)
    return db_booking

def get_owner_upcoming_bookings(db: Session, owner_id: int):
    now = datetime.now()
    return db.query(models.Booking)
             .join(models.Service)
             .filter(models.Booking.owner_id == owner_id, models.Booking.booking_time >= now)
             .order_by(models.Booking.booking_time)
             .all()

def update_owner_profile(db: Session, owner: models.Owner, owner_update: schemas.OwnerProfileUpdate):
    for field, value in owner_update.model_dump(exclude_unset=True).items():
        setattr(owner, field, value)
    db.commit()
    db.refresh(owner)
    return owner

def get_owner_booking_counts(db: Session, owner_id: int):
    total_bookings = db.query(func.count(models.Booking.id)).filter(models.Booking.owner_id == owner_id).scalar()
    return {"total_bookings": total_bookings}
