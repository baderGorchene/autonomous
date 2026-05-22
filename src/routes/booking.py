from fastapi import APIRouter, Depends, Form, BackgroundTasks, HTTPException, Request
from sqlalchemy.orm import Session
from datetime import datetime
from .. import models, database, notifications
from typing import Annotated

router = APIRouter()

def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("/{slug}/submit")
async def submit_booking(
    slug: str,
    background_tasks: BackgroundTasks,
    customer_name: Annotated[str, Form()],
    customer_email: Annotated[str, Form()],
    customer_phone: Annotated[str, Form()],
    service: Annotated[str, Form()],
    booking_time: Annotated[str, Form()],
    db: Session = Depends(get_db)
):
    owner = db.query(models.Owner).filter(models.Owner.slug == slug).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Business not found")

    booking_dt = datetime.fromisoformat(booking_time)
    new_booking = models.Booking(
        owner_id=owner.id,
        customer_name=customer_name,
        customer_email=customer_email,
        customer_phone=customer_phone,
        service=service,
        datetime=booking_dt
    )
    
    db.add(new_booking)
    db.commit()
    db.refresh(new_booking)

    booking_details = {
        "customer": customer_name,
        "service": service,
        "time": booking_dt.strftime("%Y-%m-%d %H:%M"),
        "phone": customer_phone
    }
    
    background_tasks.add_task(notifications.send_booking_notification, owner.email, "+1234567890", booking_details)
    
    return {"status": "success", "message": "Booking confirmed"}