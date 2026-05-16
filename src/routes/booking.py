from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from .. import models, database

router = APIRouter()

@router.get("/slots/{owner_slug}")
def get_available_slots(owner_slug: str, date: str, db: Session = Depends(lambda: database.SessionLocal())):
    owner = db.query(models.Owner).filter(models.Owner.slug == owner_slug).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")
    
    target_date = datetime.strptime(date, "%Y-%m-%d").date()
    availability = owner.availability_json.get(target_date.strftime("%A").lower())
    
    if not availability:
        return {"slots": []}
    
    booked_slots = db.query(models.Booking).filter(
        models.Booking.owner_id == owner.id,
        models.Booking.datetime >= datetime.combine(target_date, datetime.min.time()),
        models.Booking.datetime <= datetime.combine(target_date, datetime.max.time())
    ).all()
    
    booked_times = [b.datetime.strftime("%H:%M") for b in booked_slots]
    
    all_slots = []
    start = datetime.strptime(availability['start'], "%H:%M")
    end = datetime.strptime(availability['end'], "%H:%M")
    curr = start
    while curr < end:
        time_str = curr.strftime("%H:%M")
        if time_str not in booked_times:
            all_slots.append(time_str)
        curr += timedelta(minutes=30)
        
    return {"slots": all_slots}