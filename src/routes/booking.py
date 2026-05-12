from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from .. import models, database, schemas, notifications
from pydantic import BaseModel
from datetime import datetime

router = APIRouter()

class BookingCreate(BaseModel):
    owner_id: int
    customer_name: str
    customer_email: str
    customer_phone: str
    service: str
    datetime: datetime

@router.post("/submit")
async def submit_booking(booking_data: BookingCreate, background_tasks: BackgroundTasks, db: Session = Depends(lambda: database.SessionLocal())):
    owner = db.query(models.Owner).filter(models.Owner.id == booking_data.owner_id).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")

    new_booking = models.Booking(
        owner_id=booking_data.owner_id,
        customer_name=booking_data.customer_name,
        customer_email=booking_data.customer_email,
        customer_phone=booking_data.customer_phone,
        service=booking_data.service,
        datetime=booking_data.datetime
    )
    db.add(new_booking)
    db.commit()
    db.refresh(new_booking)

    # Trigger notifications in background
    details = {
        "customer": booking_data.customer_name,
        "time": booking_data.datetime.strftime("%Y-%m-%d %H:%M"),
        "service": booking_data.service
    }
    background_tasks.add_task(notifications.send_booking_notification, owner.email, "+1234567890", details)

    return {"status": "success", "booking_id": new_booking.id}