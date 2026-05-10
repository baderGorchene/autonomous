from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy.orm import Session
from .. import models, database
from datetime import datetime, timedelta

router = APIRouter()

@router.get("/{owner_slug}/availability")
def get_availability(owner_slug: str, date: str, db: Session = Depends(lambda: database.SessionLocal())):
    owner = db.query(models.Owner).filter(models.Owner.slug == owner_slug).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")
    
    target_date = datetime.strptime(date, '%Y-%m-%d').date()
    day_name = target_date.strftime('%A').lower()
    
    availability = owner.availability_json.get(day_name, [])
    booked_slots = db.query(models.Booking).filter(
        models.Booking.owner_id == owner.id, 
        models.Booking.datetime >= target_date, 
        models.Booking.datetime < target_date + timedelta(days=1)
    ).all()
    
    booked_times = [b.datetime.strftime('%H:%M') for b in booked_slots]
    available_slots = [slot for slot in availability if slot not in booked_times]
    
    return {"available_slots": available_slots}

@router.get("/{owner_slug}")
def get_booking_page(owner_slug: str, request: Request, db: Session = Depends(lambda: database.SessionLocal())):
    owner = db.query(models.Owner).filter(models.Owner.slug == owner_slug).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")
    return request.state.templates.TemplateResponse("booking_page.html", {"request": request, "owner": owner, "lang": request.state.locale})