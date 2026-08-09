from sqlalchemy.orm import Session
from sqlalchemy import and_ , func
from datetime import date, datetime, time, timedelta
from typing import List, Optional

from . import models, schemas
from .security import get_password_hash

def get_owner(db: Session, owner_id: int):
    return db.query(models.Owner).filter(models.Owner.id == owner_id).first()

def get_owner_by_email(db: Session, email: str):
    return db.query(models.Owner).filter(models.Owner.email == email).first()

def get_owners(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.Owner).offset(skip).limit(limit).all()

def create_owner(db: Session, owner: schemas.OwnerCreate):
    hashed_password = get_password_hash(owner.password)
    db_owner = models.Owner(email=owner.email, hashed_password=hashed_password, company_name=owner.company_name, phone=owner.phone)
    db.add(db_owner)
    db.commit()
    db.refresh(db_owner)
    return db_owner

def update_owner(db: Session, db_owner: models.Owner, owner_update: schemas.OwnerUpdate):
    update_data = owner_update.model_dump(exclude_unset=True)
    if "password" in update_data:
        update_data["hashed_password"] = get_password_hash(update_data["password"])
        del update_data["password"]
    for key, value in update_data.items():
        setattr(db_owner, key, value)
    db.add(db_owner)
    db.commit()
    db.refresh(db_owner)
    return db_owner

def delete_owner(db: Session, owner_id: int):
    db_owner = db.query(models.Owner).filter(models.Owner.id == owner_id).first()
    if db_owner:
        db.delete(db_owner)
        db.commit()
        return True
    return False

def get_service(db: Session, service_id: int):
    return db.query(models.Service).filter(models.Service.id == service_id).first()

def get_service_by_owner(db: Session, service_id: int, owner_id: int):
    return db.query(models.Service).filter(models.Service.id == service_id, models.Service.owner_id == owner_id).first()

def get_services(db: Session, owner_id: int, skip: int = 0, limit: int = 100):
    return db.query(models.Service).filter(models.Service.owner_id == owner_id).offset(skip).limit(limit).all()

def create_owner_service(db: Session, service: schemas.ServiceCreate, owner_id: int):
    db_service = models.Service(**service.model_dump(), owner_id=owner_id)
    db.add(db_service)
    db.commit()
    db.refresh(db_service)
    return db_service

def update_service(db: Session, db_service: models.Service, service_update: schemas.ServiceCreate):
    update_data = service_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_service, key, value)
    db.add(db_service)
    db.commit()
    db.refresh(db_service)
    return db_service

def delete_service(db: Session, service_id: int):
    db_service = db.query(models.Service).filter(models.Service.id == service_id).first()
    if db_service:
        db.delete(db_service)
        db.commit()
        return True
    return False

def get_availability(db: Session, availability_id: int):
    return db.query(models.Availability).filter(models.Availability.id == availability_id).first()

def get_service_availabilities(db: Session, service_id: int) -> List[models.Availability]:
    return db.query(models.Availability).filter(models.Availability.service_id == service_id).all()

def create_service_availability(db: Session, availability: schemas.AvailabilityCreate, owner_id: int, service_id: int):
    db_availability = models.Availability(**availability.model_dump(), owner_id=owner_id, service_id=service_id)
    db.add(db_availability)
    db.commit()
    db.refresh(db_availability)
    return db_availability

def update_availability(db: Session, db_availability: models.Availability, availability_update: schemas.AvailabilityCreate):
    update_data = availability_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_availability, key, value)
    db.add(db_availability)
    db.commit()
    db.refresh(db_availability)
    return db_availability

def delete_availability(db: Session, availability_id: int):
    db_availability = db.query(models.Availability).filter(models.Availability.id == availability_id).first()
    if db_availability:
        db.delete(db_availability)
        db.commit()
        return True
    return False

def get_booking(db: Session, booking_id: int):
    return db.query(models.Booking).filter(models.Booking.id == booking_id).first()

def get_bookings(db: Session, owner_id: int, skip: int = 0, limit: int = 100):
    return db.query(models.Booking).filter(models.Booking.owner_id == owner_id).offset(skip).limit(limit).all()

def get_bookings_for_service_in_range(db: Session, service_id: int, start_date: date, end_date: date) -> List[models.Booking]:
    # Ensure bookings are within the requested date range, considering booking start and end times
    # A booking is considered 'in range' if it overlaps with any part of the requested period.
    # The requested period is from start_date (inclusive, beginning of day) to end_date (inclusive, end of day).
    # So, a booking starting before (end_date + 1 day) and ending after (start_date) is relevant.
    return db.query(models.Booking).filter(
        models.Booking.service_id == service_id,
        and_(
            models.Booking.start_time < datetime.combine(end_date + timedelta(days=1), time.min), 
            models.Booking.end_time > datetime.combine(start_date, time.min)
        )
    ).all()

def create_booking(db: Session, booking: schemas.BookingCreate, owner_id: int, service_duration_minutes: int):
    end_time = booking.start_time + timedelta(minutes=service_duration_minutes)
    db_booking = models.Booking(**booking.model_dump(), owner_id=owner_id, end_time=end_time)
    db.add(db_booking)
    db.commit()
    db.refresh(db_booking)
    return db_booking

def update_booking(db: Session, db_booking: models.Booking, booking_update: schemas.BookingCreate):
    update_data = booking_update.model_dump(exclude_unset=True)
    if "start_time" in update_data and "service_duration_minutes" in update_data: # Assuming duration is passed for recalculation
        db_booking.end_time = update_data["start_time"] + timedelta(minutes=update_data["service_duration_minutes"])
        del update_data["service_duration_minutes"]

    for key, value in update_data.items():
        setattr(db_booking, key, value)
    db.add(db_booking)
    db.commit()
    db.refresh(db_booking)
    return db_booking

def delete_booking(db: Session, booking_id: int):
    db_booking = db.query(models.Booking).filter(models.Booking.id == booking_id).first()
    if db_booking:
        db.delete(db_booking)
        db.commit()
        return True
    return False

def get_total_bookings_month(db: Session, owner_id: int, start_of_month: datetime, end_of_month: datetime) -> int:
    return db.query(models.Booking).filter(
        models.Booking.owner_id == owner_id,
        models.Booking.start_time >= start_of_month,
        models.Booking.start_time < end_of_month
    ).count()

def get_popular_services(db: Session, owner_id: int, start_of_month: datetime, end_of_month: datetime, limit: int = 5) -> List[dict]:
    popular_services = db.query(
        models.Service.name,
        func.count(models.Booking.id).label("booking_count")
    ).join(models.Booking, models.Service.id == models.Booking.service_id).filter(
        models.Service.owner_id == owner_id,
        models.Booking.start_time >= start_of_month,
        models.Booking.start_time < end_of_month
    ).group_by(models.Service.name).order_by(func.count(models.Booking.id).desc()).limit(limit).all()
    
    return [{"service_name": name, "booking_count": count} for name, count in popular_services]

def admin_get_owner(db: Session, owner_id: int):
    return db.query(models.Owner).filter(models.Owner.id == owner_id).first()

def admin_get_owners(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.Owner).offset(skip).limit(limit).all()

def admin_update_owner(db: Session, db_owner: models.Owner, owner_update: schemas.AdminOwnerUpdate):
    update_data = owner_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_owner, key, value)
    db.add(db_owner)
    db.commit()
    db.refresh(db_owner)
    return db_owner

def admin_delete_owner(db: Session, owner_id: int):
    db_owner = db.query(models.Owner).filter(models.Owner.id == owner_id).first()
    if db_owner:
        db.delete(db_owner)
        db.commit()
        return True
    return False

def admin_get_service(db: Session, service_id: int):
    return db.query(models.Service).filter(models.Service.id == service_id).first()

def admin_get_services_by_owner(db: Session, owner_id: int, skip: int = 0, limit: int = 100):
    return db.query(models.Service).filter(models.Service.owner_id == owner_id).offset(skip).limit(limit).all()

def admin_update_service(db: Session, db_service: models.Service, service_update: schemas.AdminServiceUpdate):
    update_data = service_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_service, key, value)
    db.add(db_service)
    db.commit()
    db.refresh(db_service)
    return db_service

def admin_delete_service(db: Session, service_id: int):
    db_service = db.query(models.Service).filter(models.Service.id == service_id).first()
    if db_service:
        db.delete(db_service)
        db.commit()
        return True
    return False

def admin_get_booking(db: Session, booking_id: int):
    return db.query(models.Booking).filter(models.Booking.id == booking_id).first()

def admin_get_bookings_by_owner(db: Session, owner_id: int, skip: int = 0, limit: int = 100):
    return db.query(models.Booking).filter(models.Booking.owner_id == owner_id).offset(skip).limit(limit).all()

def admin_update_booking(db: Session, db_booking: models.Booking, booking_update: schemas.AdminBookingUpdate):
    update_data = booking_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_booking, key, value)
    db.add(db_booking)
    db.commit()
    db.refresh(db_booking)
    return db_booking

def admin_delete_booking(db: Session, booking_id: int):
    db_booking = db.query(models.Booking).filter(models.Booking.id == booking_id).first()
    if db_booking:
        db.delete(db_booking)
        db.commit()
        return True
    return False
