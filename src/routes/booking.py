from fastapi import APIRouter, Request, Depends, Form, BackgroundTasks, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional

from .. import crud, database, schemas, notifications
from ..main import TEMPLATES_DIR, PROJECT_ROOT
from ..i18n_config import get_jinja_env

router = APIRouter()

def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/{owner_slug}")
async def get_booking_page(owner_slug: str, request: Request, db: Session = Depends(get_db)):
    owner = crud.get_owner_by_slug(db, slug=owner_slug)
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")

    locale = request.query_params.get("lang", "en")
    templates_env = get_jinja_env(locale=locale, templates_dir=TEMPLATES_DIR, project_root=PROJECT_ROOT)

    return templates_env.get_template("booking_page.html").render({
        "request": request,
        "owner": owner,
        "lang": locale,
        "services": owner.services_json,
        "availability": owner.availability_json
    })

@router.post("/{owner_slug}/book")
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
    owner = crud.get_owner_by_slug(db, slug=owner_slug)
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")

    try:
        booking_datetime = datetime.fromisoformat(booking_datetime_str)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid datetime format")

    booking_schema = schemas.BookingCreate(
        customer_name=customer_name,
        customer_email=customer_email,
        customer_phone=customer_phone,
        service=service,
        datetime=booking_datetime
    )
    db_booking = crud.create_booking(db, booking=booking_schema, owner_id=owner.id)

    background_tasks.add_task(notifications.send_email_confirmation,
                              to_email=customer_email,
                              subject=f"Booking Confirmation for {owner.business_name}",
                              body=f"Hi {customer_name},\n\nYour booking for {service} on {booking_datetime.strftime('%Y-%m-%d %H:%M')} with {owner.business_name} is confirmed.\n\nThank you!")
    
    if owner.email:
        background_tasks.add_task(notifications.send_email_confirmation,
                                  to_email=owner.email,
                                  subject=f"New Booking for {owner.business_name}",
                                  body=f"Hi {owner.name},\n\nYou have a new booking from {customer_name} for {service} on {booking_datetime.strftime('%Y-%m-%d %H:%M')}.\nCustomer Email: {customer_email}\nCustomer Phone: {customer_phone}")
    
    if owner.phone:
        whatsapp_message = f"New BookSlot booking for {owner.business_name}:\nService: {service}\nDate/Time: {booking_datetime.strftime('%Y-%m-%d %H:%M')}\nCustomer: {customer_name} ({customer_phone})\nEmail: {customer_email}"
        background_tasks.add_task(notifications.send_whatsapp_notification,
                                  to_phone=owner.phone,
                                  message=whatsapp_message)

    locale = request.query_params.get("lang", "en")
    templates_env = get_jinja_env(locale=locale, templates_dir=TEMPLATES_DIR, project_root=PROJECT_ROOT)
    return templates_env.get_template("booking_confirmation.html").render({
        "request": request,
        "booking": db_booking,
        "owner": owner,
        "lang": locale
    })
