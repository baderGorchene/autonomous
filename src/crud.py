from sqlalchemy.orm import Session
from . import models, schemas
import uuid
from datetime import datetime, date, time, timedelta
from typing import List, Optional


def get_owner(db: Session, owner_id: uuid.UUID):
    return db.query(models.Owner).filter(models.Owner.id == owner_id).first()

def get_owner_by_email(db: Session, email: str):
    return db.query(models.Owner).filter(models.Owner.email == email).first()

def get_service(db: Session, service_id: uuid.UUID):
    return db.query(models.Service).filter(models.Service.id == service_id).first()

def get_availabilities_by_owner_and_day(db: Session, owner_id: uuid.UUID, day_of_week: int) -> List[models.Availability]:
    return db.query(models.Availability).filter(
        models.Availability.owner_id == owner_id,
        models.Availability.day_of_week == day_of_week,
        models.Availability.is_available == True
    ).order_by(models.Availability.start_time).all()

def create_booking(db: Session, booking: models.Booking):
    db.add(booking)
    db.commit()
    db.refresh(booking)
    return booking

def get_booking(db: Session, booking_id: uuid.UUID):
    return db.query(models.Booking).filter(models.Booking.id == booking_id).first()

def get_overlapping_bookings(db: Session, owner_id: uuid.UUID, service_id: uuid.UUID, start_time: datetime, end_time: datetime) -> List[models.Booking]:
    return db.query(models.Booking).filter(
        models.Booking.owner_id == owner_id,
        models.Booking.service_id == service_id,
        models.Booking.status == "confirmed",
        models.Booking.start_time < end_time,
        models.Booking.end_time > start_time
    ).all()

def create_recurring_bookings(db: Session, booking_data: schemas.RecurringBookingCreate, owner_id: uuid.UUID) -> List[models.Booking]:
    """
    Creates a series of bookings based on a recurring pattern.
    Assumes schemas.RecurringBookingCreate includes all fields of schemas.BookingCreate
    plus 'recurrence_pattern' and 'recurrence_end_date'.
    """
    
    # Create the initial booking (the "parent" booking for recurrence)
    initial_booking = models.Booking(
        id=uuid.uuid4(),
        owner_id=owner_id,
        service_id=booking_data.service_id,
        customer_name=booking_data.customer_name,
        customer_email=booking_data.customer_email,
        customer_phone=booking_data.customer_phone,
        start_time=booking_data.start_time,
        end_time=booking_data.end_time,
        status="pending", # Default status, can be refined based on business logic (e.g., payment)
        is_recurring=True,
        recurrence_pattern=booking_data.recurrence_pattern,
        recurrence_end_date=booking_data.recurrence_end_date,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    db.add(initial_booking)
    db.flush() # Flush to get the ID for initial_booking before committing, needed for original_booking_id
    
    created_bookings = [initial_booking]
    
    current_start_time = booking_data.start_time
    current_end_time = booking_data.end_time
    
    # Simple recurrence logic: currently supports 'weekly' and 'daily'
    if booking_data.recurrence_pattern == "weekly":
        while True:
            next_start_time = current_start_time + timedelta(weeks=1)
            next_end_time = current_end_time + timedelta(weeks=1)
            
            # Stop if the next occurrence goes beyond the recurrence end date
            # Compare dates only, ignore time part for recurrence_end_date
            if next_start_time.date() > booking_data.recurrence_end_date:
                break
            
            # Create a new booking occurrence linked to the parent
            recurring_occurrence = models.Booking(
                id=uuid.uuid4(),
                owner_id=owner_id,
                service_id=booking_data.service_id,
                customer_name=booking_data.customer_name,
                customer_email=booking_data.customer_email,
                customer_phone=booking_data.customer_phone,
                start_time=next_start_time,
                end_time=next_end_time,
                status="pending",
                is_recurring=True,
                original_booking_id=initial_booking.id, # Link to the parent booking
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            db.add(recurring_occurrence)
            created_bookings.append(recurring_occurrence)
            
            current_start_time = next_start_time
            current_end_time = next_end_time
    elif booking_data.recurrence_pattern == "daily":
        while True:
            next_start_time = current_start_time + timedelta(days=1)
            next_end_time = current_end_time + timedelta(days=1)
            
            if next_start_time.date() > booking_data.recurrence_end_date:
                break
            
            recurring_occurrence = models.Booking(
                id=uuid.uuid4(),
                owner_id=owner_id,
                service_id=booking_data.service_id,
                customer_name=booking_data.customer_name,
                customer_email=booking_data.customer_email,
                customer_phone=booking_data.customer_phone,
                start_time=next_start_time,
                end_time=next_end_time,
                status="pending",
                is_recurring=True,
                original_booking_id=initial_booking.id,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            db.add(recurring_occurrence)
            created_bookings.append(recurring_occurrence)
            
            current_start_time = next_start_time
            current_end_time = next_end_time
    # Future expansion could include 'monthly', 'yearly', or RRule parsing
    
    db.commit()
    for booking in created_bookings:
        db.refresh(booking)
    return created_bookings
