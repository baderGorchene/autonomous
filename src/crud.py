import json
import calendar
from sqlalchemy.orm import Session
from . import models, schemas, security
from sqlalchemy.exc import IntegrityError
from datetime import datetime, time

def get_owner(db: Session, owner_id: int):
    return db.query(models.Owner).filter(models.Owner.id == owner_id).first()

def get_owner_by_email(db: Session, email: str):
    return db.query(models.Owner).filter(models.Owner.email == email).first()

def get_owner_by_slug(db: Session, slug: str):
    return db.query(models.Owner).filter(models.Owner.slug == slug).first()

def get_owners(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.Owner).offset(skip).limit(limit).all()

def create_owner(db: Session, owner: schemas.OwnerCreate):
    # Check for existing slug to prevent conflicts and provide user-friendly error
    if get_owner_by_slug(db, owner.slug):
        raise ValueError("Slug already in use. Please choose a different one.")
    
    # Check for existing email to prevent duplicate accounts
    if get_owner_by_email(db, owner.email):
        raise ValueError("Email already registered. Please use a different email or log in.")

    hashed_password = security.get_password_hash(owner.password)
    db_owner = models.Owner(name=owner.name, email=owner.email, hashed_password=hashed_password, business_name=owner.business_name, slug=owner.slug, services_json="[]", availability_json="{}", phone=owner.phone)
    db.add(db_owner)
    try:
        db.commit()
        db.refresh(db_owner)
    except IntegrityError:
        db.rollback()
        # This catch is for potential race conditions or other database integrity errors
        raise ValueError("A database conflict occurred during owner creation. Please try again.")
    return db_owner

def authenticate_owner(db: Session, email: str, password: str):
    owner = get_owner_by_email(db, email)
    if not owner:
        return False
    if not security.verify_password(password, owner.hashed_password):
        return False
    return owner

def create_booking(db: Session, booking: schemas.BookingCreate, owner_id: int):
    # Validate that the booking date and time are not in the past
    booking_datetime = datetime.combine(booking.booking_date, booking.booking_time)
    if booking_datetime < datetime.now():
        raise ValueError("Cannot book a time slot in the past.")

    # Get owner to check availability and services
    owner = db.query(models.Owner).filter(models.Owner.id == owner_id).first()
    if not owner:
        raise ValueError("Owner not found.")

    # Parse owner's availability
    try:
        availability_data = json.loads(owner.availability_json)
        available_slots_by_day = availability_data.get("slots", {})
    except json.JSONDecodeError:
        raise ValueError("Owner's availability data is malformed.")

    # Determine day of week for booking
    day_name = calendar.day_name[booking.booking_date.weekday()] # e.g., "Monday"
    
    # Check if the requested slot is available for that day
    day_slots = available_slots_by_day.get(day_name, [])
    
    # Convert booking_time to string "HH:MM" for comparison with stored slots
    booking_time_str = booking.booking_time.strftime("%H:%M")

    if booking_time_str not in day_slots:
        raise ValueError(f"The requested time slot {booking_time_str} on {day_name} is not available for booking.")

    # --- NEW LOGIC: Retrieve service duration and include in booking --- 
    service_duration_minutes = 0
    try:
        services_data = json.loads(owner.services_json)
        selected_service = next((s for s in services_data if s["name"] == booking.service_name), None)
        if not selected_service:
            raise ValueError(f"Service '{booking.service_name}' not found for this owner.")
        service_duration_minutes = selected_service.get("duration_minutes")
        if not service_duration_minutes or not isinstance(service_duration_minutes, int) or service_duration_minutes <= 0:
            raise ValueError(f"Service '{booking.service_name}' has an invalid or missing duration. Please contact the owner.")
    except (json.JSONDecodeError, ValueError) as e:
        raise ValueError(f"Error processing service details for booking: {e}")
    # --- END NEW LOGIC ---

    # Check for existing bookings at the same time for this owner
    # This check still only prevents exact start time overlaps. Duration-based overlap
    # will be implemented in a future task.
    existing_booking = db.query(models.Booking).filter(
        models.Booking.owner_id == owner_id,
        models.Booking.booking_date == booking.booking_date,
        models.Booking.booking_time == booking.booking_time
    ).first()

    if existing_booking:
        raise ValueError("This time slot is already booked. Please choose another time.")

    # Create the booking with the retrieved service duration
    db_booking = models.Booking(**booking.model_dump(), owner_id=owner_id, service_duration_minutes=service_duration_minutes)
    db.add(db_booking)
    db.commit()
    db.refresh(db_booking)
    return db_booking

def update_owner_profile(db: Session, current_owner: models.Owner, owner_update: schemas.OwnerProfileUpdate):
    current_owner.name = owner_update.name
    current_owner.business_name = owner_update.business_name
    current_owner.phone = owner_update.phone
    
    # Update services_json and availability_json if provided
    if owner_update.services_json is not None:
        try:
            # Validate the incoming services_json against the ServiceSchema
            services_data = json.loads(owner_update.services_json)
            # Ensure it's a list, even if empty
            if not isinstance(services_data, list):
                raise ValueError("services_json must be a JSON array of services.")
            # Validate each service item against ServiceSchema
            validated_services = [schemas.ServiceSchema(**service) for service in services_data]
            current_owner.services_json = json.dumps([s.model_dump() for s in validated_services])
        except (json.JSONDecodeError, ValueError) as e:
            raise ValueError(f"Invalid services data: {e}")
    if owner_update.availability_json is not None:
        current_owner.availability_json = owner_update.availability_json

    db.add(current_owner)
    db.commit()
    db.refresh(current_owner)
    return current_owner

def get_owner_bookings(db: Session, owner_id: int):
    return db.query(models.Booking).filter(models.Booking.owner_id == owner_id).order_by(models.Booking.booking_date, models.Booking.booking_time).all()
