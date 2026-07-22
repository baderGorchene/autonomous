from fastapi import APIRouter, Request, Depends, Form, BackgroundTasks, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional
from .. import models, schemas, crud, database, notifications
import os

router = APIRouter()

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
TEMPLATES_DIR = os.path.join(PROJECT_ROOT, "templates")

def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/{owner_slug}")
async def get_booking_page(owner_slug: str, request: Request, db: Session = Depends(get_db)):
    owner = crud.get_owner_by_slug(db, owner_slug)
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")
    
    return request.state.templates.TemplateResponse("booking_page.html", {
        "request": request,
        "owner": owner,
        "lang": request.state.locale
    })

@router.post("/{owner_slug}/submit")
async def submit_booking(
    owner_slug: str,
    request: Request,
    background_tasks: BackgroundTasks,
    service: str = Form(...),
    date: str = Form(...),
    time: str = Form(...),
    customer_name: str = Form(...),
    customer_email: str = Form(...),
    customer_phone: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    owner = crud.get_owner_by_slug(db, owner_slug)
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")

    try:
        booking_datetime = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date or time format")

    booking_schema = schemas.BookingCreate(
        customer_name=customer_name,
        customer_email=customer_email,
        customer_phone=customer_phone,
        service=service,
        datetime=booking_datetime
    )

    db_booking = crud.create_booking(db, booking_schema, owner.id)

    # Send notifications in background
    background_tasks.add_task(
        notifications.send_email_confirmation,
        to_email=customer_email,
        subject=f"Booking Confirmation with {owner.business_name}",
        body=f"Hi {customer_name},\n\nYour booking for {service} on {booking_datetime.strftime('%Y-%m-%d %H:%M')} with {owner.business_name} has been confirmed.\n\nBest regards,\n{owner.business_name}"
    )
    if owner.phone: # Notify owner via WhatsApp
         background_tasks.add_task(
            notifications.send_whatsapp_notification,
            to_phone=owner.phone,
            message=f"New booking for {service} on {booking_datetime.strftime('%Y-%m-%d %H:%M')} from {customer_name} ({customer_phone})."
        )
    
    return request.state.templates.TemplateResponse("booking_confirmation.html", {
        "request": request,
        "booking": db_booking,
        "owner": owner,
        "lang": request.state.locale
    })
