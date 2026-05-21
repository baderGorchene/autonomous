from fastapi import APIRouter, Depends, BackgroundTasks, Form
from sqlalchemy.orm import Session
from .. import models, database, notifications

router = APIRouter()

def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("/{slug}/create")
async def create_booking(slug: str, background_tasks: BackgroundTasks, 
                         name: str = Form(...), email: str = Form(...), 
                         phone: str = Form(...), service: str = Form(...), 
                         time: str = Form(...), db: Session = Depends(get_db)):
    owner = db.query(models.Owner).filter(models.Owner.slug == slug).first()
    if not owner:
        return {"error": "Business not found"}
    
    new_booking = models.Booking(owner_id=owner.id, customer_name=name, customer_email=email, 
                                 customer_phone=phone, service=service, datetime=time)
    db.add(new_booking)
    db.commit()
    db.refresh(new_booking)

    booking_details = {"customer": name, "time": time, "service": service}
    background_tasks.add_task(notifications.send_booking_notification, owner.email, owner.phone, booking_details)
    
    return {"status": "success", "message": "Booking confirmed"}