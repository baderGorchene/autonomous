from datetime import datetime, date, timedelta
from typing import List, Optional
import uuid
from fastapi import HTTPException
from sqlalchemy.orm import Session

from . import models, schemas

def generate_recurring_bookings(
    booking_data: schemas.BookingCreate,
    owner_id: int,
    db: Session,
    service: models.Service
) -> List[models.Booking]:
    """
    Generates a list of individual booking instances based on recurrence pattern.
    Performs availability checks for each instance.
    """
    bookings_to_create = []
    current_start_time = booking_data.start_time
    current_end_time = booking_data.end_time
    recurrence_group_id = str(uuid.uuid4())

    if not booking_data.recurrence_pattern or not booking_data.recurrence_end_date:
        raise ValueError("Recurrence pattern and end date must be provided for recurring bookings.")

    # Ensure current_start_time is timezone-aware if needed, or consistent as naive.
    # For simplicity, assuming naive datetimes are handled consistently.

    while current_start_time.date() <= booking_data.recurrence_end_date:
        # Check for conflicts for the current recurring slot
        existing_bookings = db.query(models.Booking).filter(
            models.Booking.owner_id == owner_id,
            models.Booking.start_time < current_end_time,
            models.Booking.end_time > current_start_time,
            models.Booking.status != "cancelled" # Ignore cancelled bookings for conflict check
        ).first()

        if existing_bookings:
            # For simplicity, if any recurring slot conflicts, fail the entire series.
            # A more advanced implementation might skip conflicting slots or offer alternatives.
            raise HTTPException(status_code=409, detail=f"A recurring slot conflicts with an existing booking at {current_start_time.isoformat()}")

        booking_instance = models.Booking(
            customer_name=booking_data.customer_name,
            customer_email=booking_data.customer_email,
            customer_phone=booking_data.customer_phone,
            start_time=current_start_time,
            end_time=current_end_time,
            service_id=booking_data.service_id,
            owner_id=owner_id,
            is_recurring=True,
            recurrence_pattern=booking_data.recurrence_pattern,
            recurrence_end_date=booking_data.recurrence_end_date,
            recurrence_group_id=recurrence_group_id
        )
        bookings_to_create.append(booking_instance)

        # Move to the next recurrence
        if booking_data.recurrence_pattern == "daily":
            current_start_time += timedelta(days=1)
            current_end_time += timedelta(days=1)
        elif booking_data.recurrence_pattern == "weekly":
            current_start_time += timedelta(weeks=1)
            current_end_time += timedelta(weeks=1)
        elif booking_data.recurrence_pattern == "bi-weekly":
            current_start_time += timedelta(weeks=2)
            current_end_time += timedelta(weeks=2)
        elif booking_data.recurrence_pattern == "monthly":
            # This is a bit more complex. Simple approach: add 30 days.
            # A more robust approach would handle month-end correctly.
            current_start_time += timedelta(days=30)
            current_end_time += timedelta(days=30)
        else:
            raise ValueError(f"Unsupported recurrence pattern: {booking_data.recurrence_pattern}")

    return bookings_to_create
