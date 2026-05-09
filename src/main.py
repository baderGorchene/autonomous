from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, time, date
from . import models, schemas, database

app = FastAPI()

models.Base.metadata.create_all(bind=database.engine)

def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get('/{slug}/availability')
def get_availability(slug: str, date_str: str, duration: int, db: Session = Depends(get_db)):
    owner = db.query(models.Owner).filter(models.Owner.slug == slug).first()
    if not owner: raise HTTPException(status_code=404)
    
    target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    day_of_week = target_date.weekday()
    
    avail_rules = [a for a in owner.availability_json if a['day_of_week'] == day_of_week]
    booked_bookings = db.query(models.Booking).filter(
        models.Booking.owner_id == owner.id,
        models.Booking.datetime >= datetime.combine(target_date, time.min),
        models.Booking.datetime <= datetime.combine(target_date, time.max)
    ).all()

    booked_ranges = []
    for b in booked_bookings:
        svc = next((s for s in owner.services_json if s['name'] == b.service), None)
        dur = svc['duration_minutes'] if svc else 30
        start = b.datetime
        end = start + timedelta(minutes=dur)
        booked_ranges.append((start, end))

    available_slots = []
    for rule in avail_rules:
        start_t = datetime.strptime(rule['start_time'], '%H:%M:%S').time()
        end_t = datetime.strptime(rule['end_time'], '%H:%M:%S').time()
        
        curr = datetime.combine(target_date, start_t)
        end_limit = datetime.combine(target_date, end_t)
        
        while curr + timedelta(minutes=duration) <= end_limit:
            slot_end = curr + timedelta(minutes=duration)
            overlap = any(curr < b_end and slot_end > b_start for b_start, b_end in booked_ranges)
            if not overlap:
                available_slots.append({'start': curr.isoformat(), 'end': slot_end.isoformat()})
            curr += timedelta(minutes=15)
            
    return {"date": date_str, "slots": available_slots}