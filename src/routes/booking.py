from fastapi import APIRouter, Depends, Form, BackgroundTasks, HTTPException, Request
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
def get_booking_page(request: Request, slug: str, db: Session = Depends(get_db)):
    owner = db.query(models.Owner).filter(models.Owner.slug == slug).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Business not found")
    
    return request.state.templates.TemplateResponse("booking.html", {
        "request": request, 
        "owner": owner, 
        "lang": request.state.locale
    })

@router.post("/{slug}/submit")
async def submit_booking(
    slug: str,
    background_tasks: BackgroundTasks,
    name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(...),
    service: str = Form(...),
    date_time: str = Form(...),
    db: Session = Depends(get_db)
):
    owner = db.query(models.Owner).filter(models.Owner.slug == slug).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Business not found")

    booking = models.Booking(
        owner_id=owner.id,
        customer_name=name,
        customer_email=email,
        customer_phone=phone,
        service=service,
        datetime=datetime.fromisoformat(date_time)
    )
    db.add(booking)
    db.commit()
    
    booking_details = {
        "customer": name,
        "time": date_time,
        "service": service
    }
    
    background_tasks.add_task(notifications.send_booking_notification, owner.email, "+1234567890", booking_details)
    
    return {"status": "success", "message": "Booking confirmed"}