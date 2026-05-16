from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request
from sqlalchemy.orm import Session
from datetime import datetime
from .. import models, database, schemas, notifications

router = APIRouter()

@router.get("/slots/{owner_slug}")
def get_booking_page(owner_slug: str, request: Request, db: Session = Depends(lambda: database.SessionLocal())):
    owner = db.query(models.Owner).filter(models.Owner.slug == owner_slug).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")
    
    return request.state.templates.TemplateResponse("booking_form.html", {
        "request": request, 
        "owner": owner, 
        "lang": request.state.locale
    })

@router.post("/slots/{owner_slug}", status_code=201)
def create_booking(
    owner_slug: str, 
    booking_data: schemas.BookingCreate, 
    background_tasks: BackgroundTasks, 
    db: Session = Depends(lambda: database.SessionLocal())
):
    owner = db.query(models.Owner).filter(models.Owner.slug == owner_slug).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")
    
    new_booking = models.Booking(
        owner_id=owner.id,
        customer_name=booking_data.customer_name,
        customer_email=booking_data.customer_email,
        customer_phone=booking_data.customer_phone,
        service=booking_data.service,
        datetime=booking_data.datetime
    )
    db.add(new_booking)
    db.commit()
    db.refresh(new_booking)
    
    background_tasks.add_task(
        notifications.send_booking_notification,
        owner.email,
        getattr(owner, 'phone', None),
        {"customer": new_booking.customer_name, "time": new_booking.datetime.strftime("%Y-%m-%d %H:%M")}
    )
    
    return {"status": "success", "booking_id": new_booking.id}