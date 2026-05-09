from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, time
from . import models, schemas, database, notifications

app = FastAPI()

models.Base.metadata.create_all(bind=database.engine)

def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.post('/register', response_model=dict)
def register_owner(owner_data: schemas.OwnerCreate, db: Session = Depends(get_db)):
    if db.query(models.Owner).filter(models.Owner.slug == owner_data.slug).first():
        raise HTTPException(status_code=400, detail="Slug already registered")
        
    new_owner = models.Owner(
        name=owner_data.name,
        email=owner_data.email,
        business_name=owner_data.business_name,
        slug=owner_data.slug,
        services_json=[s.model_dump() for s in owner_data.services],
        availability_json=[a.model_dump(mode='json') for a in owner_data.availability]
    )
    db.add(new_owner)
    db.commit()
    db.refresh(new_owner)
    return {"message": "Owner registered successfully", "slug": new_owner.slug}

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
    
    service = next((s for s in owner.services_json if s['name'] == booking.service_name), None)
    if not service:
        raise HTTPException(status_code=400, detail="Service not found")
    
    duration = service['duration_minutes']
    booking_end = booking.datetime + timedelta(minutes=duration)
    
    overlapping = db.query(models.Booking).filter(
        models.Booking.owner_id == owner.id,
        models.Booking.datetime < booking_end,
        models.Booking.datetime + timedelta(minutes=duration) > booking.datetime
    ).first()
    
    if overlapping:
        raise HTTPException(status_code=400, detail="Time slot already booked")
    
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