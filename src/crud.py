from sqlalchemy.orm import Session
from datetime import datetime, timedelta, date
from typing import List, Optional
from fastapi import HTTPException, status

from . import models, schemas
from .security import get_password_hash # For owner creation

# --- Owner CRUD --- 
def get_owner(db: Session, owner_id: int):
    return db.query(models.Owner).filter(models.Owner.id == owner_id).first()

def get_owner_by_email(db: Session, email: str):
    return db.query(models.Owner).filter(models.Owner.email == email).first()

def get_owner_by_owner_name(db: Session, owner_name: str):
    return db.query(models.Owner).filter(models.Owner.owner_name == owner_name).first()

def create_owner(db: Session, owner: schemas.OwnerCreate):
    hashed_password = get_password_hash(owner.password)
    db_owner = models.Owner(
        email=owner.email,
        hashed_password=hashed_password,
        owner_name=owner.owner_name,
        owner_phone=owner.owner_phone,
        currency=owner.currency
    )
    db.add(db_owner)
    db.commit()
    db.refresh(db_owner)
    return db_owner

def update_owner(db: Session, owner_id: int, owner_update: schemas.OwnerUpdate):
    db_owner = get_owner(db, owner_id)
    if not db_owner:
        return None
    update_data = owner_update.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_owner, key, value)
    db.add(db_owner)
    db.commit()
    db.refresh(db_owner)
    return db_owner

# --- Service CRUD ---
def get_service(db: Session, service_id: int):
    return db.query(models.Service).filter(models.Service.id == service_id).first()

def get_services_by_owner(db: Session, owner_id: int):
    return db.query(models.Service).filter(models.Service.owner_id == owner_id).all()

def create_service(db: Session, service: schemas.ServiceCreate, owner_id: int):
    db_service = models.Service(**service.dict(), owner_id=owner_id)
    db.add(db_service)
    db.commit()
    db.refresh(db_service)
    return db_service

# --- Booking CRUD ---
def get_booking(db: Session, booking_id: int):
    return db.query(models.Booking).filter(models.Booking.id == booking_id).first()

def get_owner_bookings(db: Session, owner_id: int, skip: int = 0, limit: int = 100):
    return db.query(models.Booking).filter(models.Booking.owner_id == owner_id).offset(skip).limit(limit).all()

def get_upcoming_owner_bookings(db: Session, owner_id: int):
    now = datetime.utcnow()
    return db.query(models.Booking).filter(
        models.Booking.owner_id == owner_id,
        models.Booking.start_time >= now
    ).order_by(models.Booking.start_time).all()

def create_booking(db: Session, booking: schemas.BookingCreate, owner_id: int, is_recurring: bool = False, parent_recurring_booking_id: Optional[str] = None):
    service = get_service(db, booking.service_id)
    if not service:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")

    booking_duration = service.duration_minutes # Use service's duration
    end_time = booking.start_time + timedelta(minutes=booking_duration)

    db_booking = models.Booking(
        owner_id=owner_id,
        service_id=booking.service_id,
        customer_name=booking.customer_name,
        customer_email=booking.customer_email,
        customer_phone=booking.customer_phone,
        start_time=booking.start_time,
        end_time=end_time,
        status="confirmed", # Default status
        is_recurring=is_recurring,
        parent_recurring_booking_id=parent_recurring_booking_id
    )
    db.add(db_booking)
    db.commit()
    db.refresh(db_booking)
    return db_booking

def check_availability(db: Session, service_id: int, start_time: datetime, end_time: datetime) -> bool:
    """
    Checks if a service is available at the given time slot.
    This includes checking for conflicting bookings.
    (Future: Integrate with a robust Availability model for service working hours/days)
    """
    # For MVP, only check for conflicting bookings. 
    # A more robust system would involve a dedicated `Availability` model to check working hours.

    conflicting_bookings = db.query(models.Booking).filter(
        models.Booking.service_id == service_id,
        models.Booking.status == "confirmed", # Only confirmed bookings block slots
        models.Booking.start_time < end_time,
        models.Booking.end_time > start_time
    ).first()

    return conflicting_bookings is None

# --- Analytics CRUD ---
def get_total_bookings_count(db: Session, owner_id: int) -> int:
    return db.query(models.Booking).filter(models.Booking.owner_id == owner_id).count()

def get_upcoming_bookings_count(db: Session, owner_id: int) -> int:
    now = datetime.utcnow()
    return db.query(models.Booking).filter(
        models.Booking.owner_id == owner_id,
        models.Booking.start_time >= now
    ).count()

def get_monthly_bookings_data(db: Session, owner_id: int, num_months: int = 6) -> List[schemas.MonthlyBookingsData]:
    # This is a simplified aggregation. For production, consider database-specific functions
    # or a more efficient approach for large datasets.
    monthly_data = []
    current_date = datetime.utcnow()
    for i in range(num_months):
        month_start = (current_date.replace(day=1) - timedelta(days=1)).replace(day=1) if i > 0 else current_date.replace(day=1)
        month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        
        count = db.query(models.Booking).filter(
            models.Booking.owner_id == owner_id,
            models.Booking.start_time >= month_start,
            models.Booking.start_time < month_end + timedelta(days=1)
        ).count()
        monthly_data.append(schemas.MonthlyBookingsData(month=month_start.strftime("%Y-%m"), count=count))
        current_date = month_start - timedelta(days=1)
    return list(reversed(monthly_data))

def get_popular_services_data(db: Session, owner_id: int, limit: int = 5) -> List[schemas.PopularServiceData]:
    # This is a simplified aggregation.
    service_counts = db.query(models.Service.name, models.func.count(models.Booking.id)).\
        join(models.Booking).\
        filter(models.Service.owner_id == owner_id).\
        group_by(models.Service.name).\
        order_by(models.func.count(models.Booking.id).desc()).\
        limit(limit).all()
    
    return [schemas.PopularServiceData(service_name=name, booking_count=count) for name, count in service_counts]

# --- Admin CRUD (minimal) ---
def get_all_owners(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.Owner).offset(skip).limit(limit).all()

def delete_owner(db: Session, owner_id: int):
    db_owner = db.query(models.Owner).filter(models.Owner.id == owner_id).first()
    if db_owner:
        db.delete(db_owner)
        db.commit()
        return True
    return False
