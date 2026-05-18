from fastapi import APIRouter, Depends, Form, BackgroundTasks, HTTPException, Request
from sqlalchemy.orm import Session
from .. import models, database, notifications
from datetime import datetime

router = APIRouter()

def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/{slug}")
def get_booking_page(slug: str, request: Request, db: Session = Depends(get_db)):
    owner = db.query(models.Owner).filter(models.Owner.slug == slug).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Booking page not found")
    
    return request.state.templates.TemplateResponse("booking.html", {
        "request": request, 
        "owner": owner, 
        "lang": request.state.locale
    })

@router.post("/{slug}/submit")
async def submit_booking(
    slug: str, 
    background_tasks: BackgroundTasks, 
    customer_name: str = Form(...),
    customer_email: str = Form(...),
    customer_phone: str = Form(...),
    service: str = Form(...),
    booking_time: str = Form(...),
    db: Session = Depends(get_db)
):
    owner = db.query(models.Owner).filter(models.Owner.slug == slug).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Booking page not found")
    
    new_booking = models.Booking(
        owner_id=owner.id,
        customer_name=customer_name,
        customer_email=customer_email,
        customer_phone=customer_phone,
        service=service,
        datetime=datetime.fromisoformat(booking_time)
    )
    db.add(new_booking)
    db.commit()
    db.refresh(new_booking)
    
    details = {
        "customer": customer_name,
        "time": booking_time,
        "service": service
    }
    
    background_tasks.add_task(notifications.send_booking_notification, owner.email, "+1234567890", details)
    
    return {"status": "success", "message": "Booking confirmed"}