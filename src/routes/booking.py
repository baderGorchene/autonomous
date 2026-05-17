from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
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
async def render_booking_page(slug: str, request: Request, db: Session = Depends(get_db)):
    owner = db.query(models.Owner).filter(models.Owner.slug == slug).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Provider not found")
    
    return request.state.templates.TemplateResponse("booking.html", {
        "request": request, 
        "owner": owner, 
        "lang": request.state.locale
    })

class BookingCreate(BaseModel):
    customer_name: str
    customer_email: EmailStr
    customer_phone: str
    service: str
    booking_datetime: datetime

@router.post("/{slug}/submit", status_code=201)
async def submit_booking(slug: str, data: BookingCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    owner = db.query(models.Owner).filter(models.Owner.slug == slug).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Provider not found")
    
    new_booking = models.Booking(
        owner_id=owner.id,
        customer_name=data.customer_name,
        customer_email=data.customer_email,
        customer_phone=data.customer_phone,
        service=data.service,
        datetime=data.booking_datetime
    )
    db.add(new_booking)
    db.commit()
    db.refresh(new_booking)
    
    background_tasks.add_task(
        notifications.send_booking_notification,
        owner_email=owner.email,
        owner_phone=getattr(owner, 'phone', ""),
        booking_details={"customer": data.customer_name, "time": str(data.booking_datetime)}
    )
    
    return {"status": "success", "booking_id": new_booking.id}