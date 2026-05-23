from fastapi import APIRouter, Depends, Form, BackgroundTasks, HTTPException
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
    booking_datetime: Annotated[str, Form()],
    db: Session = Depends(get_db)
):
    owner = db.query(models.Owner).filter(models.Owner.slug == slug).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")

    dt = datetime.fromisoformat(booking_datetime)
    
    new_booking = models.Booking(
        owner_id=owner.id,
        customer_name=customer_name,
        customer_email=customer_email,
        customer_phone=customer_phone,
        service=service,
        datetime=dt
    )
    
    db.add(new_booking)
    db.commit()
    db.refresh(new_booking)

    booking_details = {
        "customer": customer_name,
        "time": dt.strftime("%Y-%m-%d %H:%M"),
        "service": service
    }

    background_tasks.add_task(
        notifications.send_booking_notification, 
        owner.email, 
        getattr(owner, 'phone', None), 
        booking_details
    )

    return {"status": "success", "message": "Booking confirmed"}