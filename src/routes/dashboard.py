from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from .. import models, database

router = APIRouter()

class BookingStatusUpdate(BaseModel):
    status: str

def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.put("/bookings/{booking_id}/status")
def update_booking_status(booking_id: int, update: BookingStatusUpdate, db: Session = Depends(get_db)):
    booking = db.query(models.Booking).filter(models.Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    
    if update.status not in ["confirmed", "cancelled", "pending"]:
        raise HTTPException(status_code=400, detail="Invalid status")
    
    booking.status = update.status
    db.commit()
    db.refresh(booking)
    return {"status": "updated", "booking_id": booking.id, "new_status": booking.status}