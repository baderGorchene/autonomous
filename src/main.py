from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
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
def get_availability(slug: str, date: str, db: Session = Depends(get_db)):
    owner = db.query(models.Owner).filter(models.Owner.slug == slug).first()
    if not owner: raise HTTPException(status_code=404)
    
    target_date = datetime.strptime(date, '%Y-%m-%d').date()
    day_of_week = target_date.weekday()
    
    avail_rules = [a for a in owner.availability_json if a['day_of_week'] == day_of_week]
    booked_slots = db.query(models.Booking).filter(models.Booking.owner_id == owner.id).all()
    
    available_slots = []
    for rule in avail_rules:
        start = datetime.strptime(rule['start_time'], '%H:%M:%S').time()
        end = datetime.strptime(rule['end_time'], '%H:%M:%S').time()
        # Logic: generate 30-min slots and check against bookings
        # Simple placeholder for slot generation logic
        available_slots.append({'start': str(start), 'end': str(end)})
        
    return {"date": date, "slots": available_slots}

@app.put('/owners/{owner_id}/services')
def update_services(owner_id: int, services: list[schemas.Service], db: Session = Depends(get_db)):
    owner = db.query(models.Owner).filter(models.Owner.id == owner_id).first()
    if not owner: raise HTTPException(status_code=404)
    owner.services_json = [s.model_dump() for s in services]
    db.commit()
    return {"status": "updated"}

@app.put('/owners/{owner_id}/availability')
def update_availability(owner_id: int, availability: list[schemas.Availability], db: Session = Depends(get_db)):
    owner = db.query(models.Owner).filter(models.Owner.id == owner_id).first()
    if not owner: raise HTTPException(status_code=404)
    owner.availability_json = [a.model_dump(mode='json') for a in availability]
    db.commit()
    return {"status": "updated"}

@app.post('/bookings', response_model=schemas.BookingResponse)
def create_booking(booking: schemas.BookingCreate, db: Session = Depends(get_db)):
    db_booking = models.Booking(**booking.model_dump())
    db.add(db_booking)
    db.commit()
    db.refresh(db_booking)
    return db_booking