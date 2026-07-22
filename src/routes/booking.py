from fastapi import APIRouter, Request, Depends, Form, BackgroundTasks, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional

from .. import crud, schemas, notifications, models
from ..database import get_db

router = APIRouter()

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

@router.post("/{owner_slug}")
async def submit_booking(
    owner_slug: str,
    request: Request,
    background_tasks: BackgroundTasks,
    customer_name: str = Form(...),
    customer_email: str = Form(...),
    customer_phone: Optional[str] = Form(None),
    service: str = Form(...),
    booking_datetime_str: str = Form(...),
    db: Session = Depends(get_db)
):
    owner = crud.get_owner_by_slug(db, owner_slug)
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")

    try:
        booking_datetime = datetime.strptime(booking_datetime_str, "%Y-%m-%dT%H:%M")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid datetime format")

    booking_data = schemas.BookingCreate(
        customer_name=customer_name,
        customer_email=customer_email,
        customer_phone=customer_phone,
        service=service,
        datetime=booking_datetime
    )

    db_booking = crud.create_booking(db, booking_data, owner.id)

    # Send notifications in background
    background_tasks.add_task(
        notifications.send_email_confirmation,
        customer_email,
        "Booking Confirmation",
        f"Hi {customer_name}, your booking for {service} on {booking_datetime.strftime('%Y-%m-%d %H:%M')} is confirmed with {owner.business_name}."
    )
    background_tasks.add_task(
        notifications.send_email_confirmation,
        owner.email,
        "New Booking Received",
        f"You have a new booking from {customer_name} for {service} on {booking_datetime.strftime('%Y-%m-%d %H:%M')}."
    )
    if owner.phone:
        background_tasks.add_task(
            notifications.send_whatsapp_notification,
            owner.phone,
            f"New booking from {customer_name} for {service} on {booking_datetime.strftime('%Y-%m-%d %H:%M')}."
        )

    return request.state.templates.TemplateResponse("booking_confirmation.html", {
        "request": request,
        "booking": db_booking,
        "owner": owner,
        "lang": request.state.locale
    })
