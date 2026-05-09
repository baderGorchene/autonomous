from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, time, date
from . import models, schemas, database, notifications
from typing import List

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
    if not owner: raise HTTPException(status_code=404, detail="Owner not found")
    
    target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    day_of_week = target_date.weekday()
    
    availability = [a for a in owner.availability_json if a['day_of_week'] == day_of_week]
    if not availability: return {"slots": []}
    
    bookings = db.query(models.Booking).filter(
        models.Booking.owner_id == owner.id,
        models.Booking.datetime >= datetime.combine(target_date, time.min),
        models.Booking.datetime <= datetime.combine(target_date, time.max)
    ).all()
    
    busy_periods = [(b.datetime, b.datetime + timedelta(minutes=duration)) for b in bookings]
    
    free_slots = []
    for av in availability:
        start_time = datetime.combine(target_date, time.fromisoformat(av['start_time']))
        end_time = datetime.combine(target_date, time.fromisoformat(av['end_time']))
        current = start_time
        
        while current + timedelta(minutes=duration) <= end_time:
            slot_end = current + timedelta(minutes=duration)
            is_busy = any(current < b_end and slot_end > b_start for b_start, b_end in busy_periods)
            if not is_busy:
                free_slots.append({"start": current.isoformat()})
            current += timedelta(minutes=30)
            
    return {"slots": free_slots}

@app.post('/{slug}/book', response_model=schemas.BookingResponse)
async def create_booking(slug: str, booking: schemas.BookingCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    owner = db.query(models.Owner).filter(models.Owner.slug == slug).first()
    if not owner: raise HTTPException(status_code=404, detail="Owner not found")
    
    db_booking = models.Booking(
        owner_id=owner.id, 
        customer_name=booking.customer_name,
        customer_email=booking.customer_email,
        customer_phone=booking.customer_phone,
        service=booking.service_name,
        datetime=booking.datetime
    )
    db.add(db_booking)
    db.commit()
    db.refresh(db_booking)
    
    background_tasks.add_task(notifications.send_booking_notification, owner.email, "", {"id": db_booking.id, "customer": booking.customer_name, "time": booking.datetime.isoformat()})
    return db_booking