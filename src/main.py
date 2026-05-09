from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, time, date
from . import models, schemas, database, notifications

app = FastAPI()

models.Base.metadata.create_all(bind=database.engine)

def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

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
    
    background_tasks.add_task(notifications.send_booking_notification, owner.email, "", {"id": db_booking.id, "customer": booking.customer_name})
    return db_booking