from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request
from sqlalchemy.orm import Session
from .. import models, database, notifications
from pydantic import BaseModel
from datetime import datetime, timedelta

router = APIRouter()

class BookingCreate(BaseModel):
    owner_id: int
    customer_name: str
    customer_email: str
    customer_phone: str
    service: str
    datetime: datetime

@router.get("/{slug}/availability")
def get_availability(slug: str, date: str, db: Session = Depends(lambda: database.SessionLocal())):
    owner = db.query(models.Owner).filter(models.Owner.slug == slug).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")
    
    # Example logic: Get bookings for the date and subtract from availability_json
    # availability_json format expected: {"monday": ["09:00", "10:00"], ...}
    target_date = datetime.strptime(date, "%Y-%m-%d")
    day_name = target_date.strftime("%A").lower()
    
    all_slots = owner.availability_json.get(day_name, [])
    booked_slots = db.query(models.Booking).filter(
        models.Booking.owner_id == owner.id,
        models.Booking.datetime >= target_date,
        models.Booking.datetime < target_date + timedelta(days=1)
    ).all()
    
    booked_times = [b.datetime.strftime("%H:%M") for b in booked_slots]
    available_slots = [s for s in all_slots if s not in booked_times]
    
    return {"available_slots": available_slots}

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