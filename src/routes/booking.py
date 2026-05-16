from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from datetime import datetime, date
from dateutil import rrule
from .. import models, database, notifications

router = APIRouter()

class BookingCreate(BaseModel):
    owner_id: int
    customer_name: str
    customer_email: EmailStr
    customer_phone: str
    service: str
    datetime: datetime

@router.get("/{slug}")
def get_booking_page(slug: str, request: Request, db: Session = Depends(lambda: database.SessionLocal())):
    owner = db.query(models.Owner).filter(models.Owner.slug == slug).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Booking page not found")
    return request.state.templates.TemplateResponse("booking_form.html", {
        "request": request, 
        "owner": owner, 
        "lang": request.state.locale
    })

@router.get("/slots/{owner_id}/{selected_date}")
def get_available_slots(owner_id: int, selected_date: str, db: Session = Depends(lambda: database.SessionLocal())):
    owner = db.query(models.Owner).filter(models.Owner.id == owner_id).first()
    if not owner or not owner.availability_json:
        return {"slots": []}
    
    target_date = datetime.strptime(selected_date, "%Y-%m-%d").date()
    booked_datetimes = [b.datetime for b in db.query(models.Booking).filter(models.Booking.owner_id == owner_id).all()]
    
    # Logic to calculate slots based on availability_json (e.g., ["09:00", "10:00"...])
    # Simplified: return slots that are not in booked_datetimes
    available = []
    for slot_str in owner.availability_json.get("slots", []):
        slot_dt = datetime.combine(target_date, datetime.strptime(slot_str, "%H:%M").time())
        if slot_dt not in booked_datetimes:
            available.append(slot_str)
            
    return {"slots": available}

@router.post("/submit")
async def submit_booking(booking_data: BookingCreate, background_tasks: BackgroundTasks, db: Session = Depends(lambda: database.SessionLocal())):
    existing_booking = db.query(models.Booking).filter(
        models.Booking.owner_id == booking_data.owner_id,
        models.Booking.datetime == booking_data.datetime
    ).first()
    
    if existing_booking:
        raise HTTPException(status_code=400, detail="This time slot is already booked.")

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

    owner = db.query(models.Owner).filter(models.Owner.id == booking_data.owner_id).first()
    booking_details = {
        "customer": booking_data.customer_name,
        "time": booking_data.datetime.isoformat(),
        "service": booking_data.service
    }
    background_tasks.add_task(notifications.send_booking_notification, owner.email, "", booking_details)

    return {"status": "success", "booking_id": new_booking.id}