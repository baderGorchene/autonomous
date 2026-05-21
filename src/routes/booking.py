from fastapi import APIRouter, Depends, BackgroundTasks, Form, Request, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from .. import models, database, notifications

router = APIRouter()

def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/{slug}")
async def show_booking_page(slug: str, request: Request, db: Session = Depends(get_db)):
    owner = db.query(models.Owner).filter(models.Owner.slug == slug).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Business not found")
    return request.state.templates.TemplateResponse("booking.html", {
        "request": request, 
        "owner": owner, 
        "lang": request.state.locale
    })

@router.post("/{slug}/create")
async def create_booking(slug: str, request: Request, background_tasks: BackgroundTasks, 
                         name: str = Form(...), email: str = Form(...), 
                         phone: str = Form(...), service: str = Form(...), 
                         time: str = Form(...), db: Session = Depends(get_db)):
    owner = db.query(models.Owner).filter(models.Owner.slug == slug).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Business not found")
    
    booking_dt = datetime.fromisoformat(time)
    new_booking = models.Booking(owner_id=owner.id, customer_name=name, customer_email=email, 
                                 customer_phone=phone, service=service, datetime=booking_dt)
    db.add(new_booking)
    db.commit()

    booking_details = {"customer": name, "time": time, "service": service}
    # Note: Added phone field to owner model if missing, assuming owner.phone exists for notifications
    background_tasks.add_task(notifications.send_booking_notification, owner.email, getattr(owner, 'phone', ''), booking_details)
    
    return request.state.templates.TemplateResponse("confirmation.html", {"request": request, "lang": request.state.locale})