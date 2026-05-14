from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from datetime import datetime
from .. import models, database, notifications

router = APIRouter()

class BookingCreate(BaseModel):
    owner_id: int
    customer_name: str
    customer_email: EmailStr
    customer_phone: str
    service: str
    datetime: datetime

@router.post("/submit")
async def submit_booking(booking_data: BookingCreate, background_tasks: BackgroundTasks, db: Session = Depends(lambda: database.SessionLocal())):
    # Save booking to DB
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

    # Fetch owner details for notification
    owner = db.query(models.Owner).filter(models.Owner.id == booking_data.owner_id).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")

    # Trigger async notification
    booking_details = {
        "customer": booking_data.customer_name,
        "time": booking_data.datetime.isoformat(),
        "service": booking_data.service
    }
    background_tasks.add_task(notifications.send_booking_notification, owner.email, "", booking_details)

    return {"status": "success", "booking_id": new_booking.id}