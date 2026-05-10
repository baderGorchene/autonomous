from fastapi import APIRouter, Depends, Request, HTTPException, BackgroundTasks, Form
from sqlalchemy.orm import Session
from .. import models, database, notifications
from datetime import datetime, timedelta

router = APIRouter()

@router.get("/{owner_slug}")
async def get_booking_page(owner_slug: str, request: Request, db: Session = Depends(lambda: database.SessionLocal())):
    owner = db.query(models.Owner).filter(models.Owner.slug == owner_slug).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Booking page not found")
    
    return request.state.templates.TemplateResponse("booking_page.html", {
        "request": request, 
        "owner": owner, 
        "lang": request.state.locale
    })

@router.post("/{owner_slug}/submit")
async def submit_booking(
    owner_slug: str,
    background_tasks: BackgroundTasks,
    customer_name: str = Form(...),
    customer_email: str = Form(...),
    customer_phone: str = Form(...),
    service: str = Form(...),
    booking_datetime: str = Form(...),
    db: Session = Depends(lambda: database.SessionLocal())
):
    owner = db.query(models.Owner).filter(models.Owner.slug == owner_slug).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")
    
    dt = datetime.fromisoformat(booking_datetime)
    new_booking = models.Booking(
        owner_id=owner.id, 
        customer_name=customer_name,
        customer_email=customer_email,
        customer_phone=customer_phone,
        service=service,
        datetime=dt
    )
    db.add(new_booking)
    db.commit()
    db.refresh(new_booking)

    booking_details = {
        "customer": customer_name,
        "time": dt.strftime('%Y-%m-%d %H:%M'),
        "service": service
    }
    
    background_tasks.add_task(
        notifications.send_booking_notification, 
        owner.email, 
        getattr(owner, 'phone', None), 
        booking_details
    )
    
    return {"status": "success", "booking_id": new_booking.id}