from fastapi import APIRouter, Depends, Form, BackgroundTasks, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from .. import models, database, notifications

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
    customer_name: str = Form(...),
    customer_email: str = Form(...),
    customer_phone: str = Form(...),
    service: str = Form(...),
    booking_time: str = Form(...),
    db: Session = Depends(get_db)
):
    owner = db.query(models.Owner).filter(models.Owner.slug == slug).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")

    booking = models.Booking(
        owner_id=owner.id,
        customer_name=customer_name,
        customer_email=customer_email,
        customer_phone=customer_phone,
        service=service,
        datetime=datetime.fromisoformat(booking_time)
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)

    booking_details = {
        "customer": customer_name,
        "time": booking.datetime.isoformat(),
        "service": service
    }
    
    background_tasks.add_task(notifications.send_booking_notification, owner.email, owner.phone if hasattr(owner, 'phone') else "", booking_details)
    
    return {"status": "success", "booking_id": booking.id}