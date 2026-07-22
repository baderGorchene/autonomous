from fastapi import APIRouter, Depends, Request, Form, BackgroundTasks, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from datetime import datetime
from src import crud, schemas, database, notifications, models
import os
from src import i18n_config

router = APIRouter()

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
TEMPLATES_DIR = os.path.join(PROJECT_ROOT, "templates")

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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Owner not found")
    
    locale = request.query_params.get("lang", "en")
    env = i18n_config.get_jinja_env(locale=locale, templates_dir=TEMPLATES_DIR, project_root=PROJECT_ROOT)
    templates = env
    
    return templates.get_template("booking_page.html").render({
        "request": request,
        "owner": owner,
        "lang": locale
    })

@router.post("/{owner_slug}/book")
async def submit_booking(
    request: Request,
    owner_slug: str,
    background_tasks: BackgroundTasks,
    customer_name: str = Form(...),
    customer_email: str = Form(...),
    customer_phone: str = Form(...),
    service: str = Form(...),
    booking_datetime_str: str = Form(...),
    db: Session = Depends(get_db)
):
    owner = crud.get_owner_by_slug(db, owner_slug)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Owner not found")

    try:
        booking_datetime = datetime.strptime(booking_datetime_str, "%Y-%m-%dT%H:%M")
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid datetime format")

    booking_create = schemas.BookingCreate(
        customer_name=customer_name,
        customer_email=customer_email,
        customer_phone=customer_phone,
        service=service,
        datetime=booking_datetime
    )
    
    db_booking = crud.create_booking(db, booking_create, owner.id)

    background_tasks.add_task(
        notifications.send_email_confirmation, 
        to_email=customer_email, 
        subject="Booking Confirmation", 
        body=f"Hi {customer_name}, your booking for {service} on {booking_datetime.strftime('%Y-%m-%d %H:%M')} with {owner.business_name} is confirmed."
    )
    background_tasks.add_task(
        notifications.send_email_confirmation, 
        to_email=owner.email, 
        subject="New Booking Received", 
        body=f"You have a new booking from {customer_name} for {service} on {booking_datetime.strftime('%Y-%m-%d %H:%M')} (Phone: {customer_phone})."
    )
    if owner.phone:
        background_tasks.add_task(
            notifications.send_whatsapp_notification,
            to_phone=owner.phone,
            message=f"New booking from {customer_name} for {service} on {booking_datetime.strftime('%Y-%m-%d %H:%M')}. Customer phone: {customer_phone}"
        )

    locale = request.query_params.get("lang", "en")
    env = i18n_config.get_jinja_env(locale=locale, templates_dir=TEMPLATES_DIR, project_root=PROJECT_ROOT)
    templates = env
    
    return templates.get_template("booking_confirmation.html").render({
        "request": request,
        "booking": db_booking,
        "owner": owner,
        "lang": locale
    })
