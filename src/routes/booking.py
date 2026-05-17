from fastapi import APIRouter, Request, Depends, HTTPException, Form, BackgroundTasks
from sqlalchemy.orm import Session
from datetime import datetime
from .. import models, database, notifications

router = APIRouter()

@router.get("/{slug}")
def get_booking_page(slug: str, request: Request, db: Session = Depends(lambda: database.SessionLocal())):
    owner = db.query(models.Owner).filter(models.Owner.slug == slug).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Business not found")
    return request.state.templates.TemplateResponse("booking_page.html", {
        "request": request, 
        "owner": owner, 
        "services": owner.services_json or [],
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
    db: Session = Depends(lambda: database.SessionLocal())
):
    owner = db.query(models.Owner).filter(models.Owner.slug == slug).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Business not found")
    
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

    booking_details = {
        "customer": customer_name,
        "service": service,
        "time": booking_time
    }

    background_tasks.add_task(
        notifications.send_booking_notification, 
        owner.email, 
        getattr(owner, 'phone', None), 
        booking_details
    )

    return {"message": "Booking successful"}