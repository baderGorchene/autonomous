from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from .. import crud, models, schemas, database, notifications
from datetime import datetime
from typing import Optional

router = APIRouter()

def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/{owner_slug}", response_class=HTMLResponse)
async def get_booking_page(request: Request, owner_slug: str, db: Session = Depends(get_db)):
    owner = crud.get_owner_by_slug(db, owner_slug)
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")
    
    return request.state.templates.TemplateResponse("booking_page.html", {
        "request": request,
        "owner": owner,
        "lang": request.state.locale
    })

@router.post("/{owner_slug}", response_class=HTMLResponse)
async def submit_booking(
    request: Request,
    owner_slug: str,
    background_tasks: BackgroundTasks,
    customer_name: str = Form(...),
    customer_email: str = Form(...),
    customer_phone: Optional[str] = Form(None),
    service: str = Form(...),
    datetime_str: str = Form(..., alias="datetime"),
    db: Session = Depends(get_db)
):
    owner = crud.get_owner_by_slug(db, owner_slug)
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")

    try:
        booking_datetime = datetime.fromisoformat(datetime_str)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid datetime format")

    booking_schema = schemas.BookingCreate(
        customer_name=customer_name,
        customer_email=customer_email,
        customer_phone=customer_phone,
        service=service,
        datetime=booking_datetime
    )
    
    db_booking = crud.create_booking(db=db, booking=booking_schema, owner_id=owner.id)

    owner_subject = f"New Booking for {owner.business_name}"
    owner_body = f"Hello {owner.name},\n\nYou have a new booking:\nCustomer: {db_booking.customer_name}\nEmail: {db_booking.customer_email}\nPhone: {db_booking.customer_phone or 'N/A'}\nService: {db_booking.service}\nWhen: {db_booking.datetime.strftime('%Y-%m-%d %H:%M')}\n\nThank you!"
    background_tasks.add_task(notifications.send_email_confirmation, owner.email, owner_subject, owner_body)
    if owner.phone:
        whatsapp_message = f"New booking for {owner.business_name}:\nCustomer: {db_booking.customer_name}\nService: {db_booking.service}\nTime: {db_booking.datetime.strftime('%Y-%m-%d %H:%M')}"
        background_tasks.add_task(notifications.send_whatsapp_notification, owner.phone, whatsapp_message)

    customer_subject = f"Your Booking Confirmation with {owner.business_name}"
    customer_body = f"Hello {db_booking.customer_name},\n\nYour booking for {db_booking.service} with {owner.business_name} on {db_booking.datetime.strftime('%Y-%m-%d %H:%M')} has been confirmed.\n\nThank you!"
    background_tasks.add_task(notifications.send_email_confirmation, db_booking.customer_email, customer_subject, customer_body)
    if db_booking.customer_phone:
        whatsapp_message = f"Hi {db_booking.customer_name}, your booking for {db_booking.service} with {owner.business_name} on {db_booking.datetime.strftime('%Y-%m-%d %H:%M')} is confirmed."
        background_tasks.add_task(notifications.send_whatsapp_notification, db_booking.customer_phone, whatsapp_message)

    return request.state.templates.TemplateResponse("booking_confirmation.html", {
        "request": request,
        "booking": db_booking,
        "owner": owner,
        "lang": request.state.locale
    })
