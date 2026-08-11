from sqlalchemy.orm import Session
from . import models, schemas
from datetime import date, time

def create_booking(db: Session, booking: schemas.BookingCreate, owner_id: int):
    db_booking = models.Booking(
        owner_id=owner_id,
        service_id=booking.service_id,
        customer_id=booking.customer_id,
        customer_name=booking.customer_name,
        customer_email=booking.customer_email,
        customer_phone=booking.customer_phone,
        date=booking.date,
        time=booking.time,
        is_recurring=booking.is_recurring,
        recurrence_id=booking.recurrence_id
    )
    db.add(db_booking)
    db.commit()
    db.refresh(db_booking)
    return db_booking

def get_owner_by_email(db: Session, email: str):
    return db.query(models.Owner).filter(models.Owner.email == email).first()

# Other CRUD functions would be here...