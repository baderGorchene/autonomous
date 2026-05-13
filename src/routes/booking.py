from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request
from sqlalchemy.orm import Session
from .. import models, database, notifications
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

@router.get("/{slug}")
def get_booking_page(slug: str, request: Request, db: Session = Depends(lambda: database.SessionLocal())):
    owner = db.query(models.Owner).filter(models.Owner.slug == slug).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Booking page not found")
    
    return request.state.templates.TemplateResponse("booking_page.html", {
        "request": request, 
        "owner": owner, 
        "lang": request.state.locale
    })

@router.put("/{booking_id}/status")
def update_booking_status(booking_id: int, status: str = Form(...), db: Session = Depends(lambda: database.SessionLocal())):
    booking = db.query(models.Booking).filter(models.Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    booking.status = status
    db.commit()
    return {"status": "updated"}

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

    details = {
        "customer": booking_data.customer_name,
        "time": booking_data.datetime.strftime("%Y-%m-%d %H:%M"),
        "service": booking_data.service
    }
    background_tasks.add_task(notifications.send_booking_notification, owner.email, "+1234567890", details)

    return {"status": "success", "booking_id": new_booking.id}