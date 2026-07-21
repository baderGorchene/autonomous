from fastapi import APIRouter, Request, Depends, Form, BackgroundTasks, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from datetime import datetime
import json

from .. import models, schemas, database, notifications

router = APIRouter()

def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/{owner_slug}", response_class=HTMLResponse)
async def get_booking_page(owner_slug: str, request: Request, db: Session = Depends(get_db)):
    owner = db.query(models.Owner).filter(models.Owner.slug == owner_slug).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")

    services = json.loads(owner.services_json) if owner.services_json else []
    availability = json.loads(owner.availability_json) if owner.availability_json else {}

    # For the MVP, we'll just show all available slots for the next 7 days.
    # In a real app, this would be dynamic based on selected service and date.
    # For now, let's just create some dummy slots based on availability_json for demonstration.
    # This logic should eventually be more robust.
    available_slots = []
    today = datetime.now().date()
    for i in range(7):
        current_date = today + timedelta(days=i)
        day_name = current_date.strftime('%A').lower() # e.g., 'monday'
        if day_name in availability:
            for slot_time in availability[day_name]:
                slot_datetime = datetime.combine(current_date, datetime.strptime(slot_time, '%H:%M').time())
                # Only add future slots
                if slot_datetime > datetime.now():
                    available_slots.append({
                        "date": current_date.strftime('%Y-%m-%d'),
                        "time": slot_time,
                        "datetime_iso": slot_datetime.isoformat()
                    })
    available_slots.sort(key=lambda x: x['datetime_iso'])

    return request.state.templates.TemplateResponse("booking_page.html", {
        "request": request,
        "owner": owner,
        "services": services,
        "available_slots": available_slots,
        "lang": request.state.locale
    })


@router.post("/{owner_slug}", response_class=HTMLResponse)
async def submit_booking(
    owner_slug: str,
    request: Request,
    background_tasks: BackgroundTasks,
    customer_name: str = Form(...),
    customer_email: str = Form(...),
    customer_phone: str = Form(...),
    service_name: str = Form(...),
    booking_datetime_iso: str = Form(...),
    db: Session = Depends(get_db)
):
    owner = db.query(models.Owner).filter(models.Owner.slug == owner_slug).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")
    
    try:
        booking_datetime = datetime.fromisoformat(booking_datetime_iso)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid datetime format")

    new_booking = models.Booking(
        owner_id=owner.id,
        customer_name=customer_name,
        customer_email=customer_email,
        customer_phone=customer_phone,
        service=service_name,
        datetime=booking_datetime,
        status="confirmed" # Or 'pending' if manual confirmation is needed
    )
    db.add(new_booking)
    db.commit()
    db.refresh(new_booking)

    booking_details = {
        "customer_name": customer_name,
        "customer_email": customer_email,
        "customer_phone": customer_phone,
        "service": service_name,
        "datetime": booking_datetime
    }

    # Send notifications in background
    background_tasks.add_task(notifications.send_booking_notification, owner.email, owner.phone, booking_details, owner.business_name)
    background_tasks.add_task(notifications.send_customer_confirmation_email, customer_email, booking_details, owner.business_name)

    return request.state.templates.TemplateResponse("booking_confirmation.html", {
        "request": request,
        "owner": owner,
        "booking": new_booking,
        "lang": request.state.locale
    })

from datetime import timedelta