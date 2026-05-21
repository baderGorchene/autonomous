from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from .. import models, database
from datetime import datetime, timedelta

router = APIRouter()

def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

def is_slot_available(owner_id: int, booking_dt: datetime, db: Session) -> bool:
    # Check if a booking already exists at this exact time
    existing = db.query(models.Booking).filter(
        models.Booking.owner_id == owner_id,
        models.Booking.datetime == booking_dt
    ).first()
    return existing is None

@router.get("/{slug}/slots")
def get_available_slots(slug: str, date: str, db: Session = Depends(get_db)):
    owner = db.query(models.Owner).filter(models.Owner.slug == slug).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")
    
    # Example availability_json format: {"09:00": true, "10:00": true}
    slots = owner.availability_json or {}
    booked_slots = db.query(models.Booking.datetime).filter(
        models.Booking.owner_id == owner.id,
        models.Booking.datetime.like(f"{date}%")
    ).all()
    
    booked_times = {b[0].strftime("%H:%M") for b in booked_slots}
    available = [s for s in slots if s not in booked_times]
    return {"slots": available}

@router.post("/{slug}/book")
def create_booking(slug: str, customer_name: str, customer_phone: str, datetime_str: str, db: Session = Depends(get_db)):
    owner = db.query(models.Owner).filter(models.Owner.slug == slug).first()
    booking_dt = datetime.strptime(datetime_str, "%Y-%m-%d %H:%M")
    
    if not is_slot_available(owner.id, booking_dt, db):
        raise HTTPException(status_code=400, detail="Slot already booked")
    
    new_booking = models.Booking(owner_id=owner.id, customer_name=customer_name, customer_phone=customer_phone, datetime=booking_dt)
    db.add(new_booking)
    db.commit()
    return {"status": "success"}