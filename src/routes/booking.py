from fastapi import APIRouter, Request, Depends, Form, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from datetime import datetime
from .. import crud, schemas, database, notifications

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
    
    templates = request.state.templates
    
    return templates.TemplateResponse("booking_page.html", {
        "request": request,
        "owner": owner,
        "lang": request.state.locale
    })

@router.post("/{owner_slug}/book", response_class=HTMLResponse)
async def submit_booking(
    request: Request,
    owner_slug: str,
    customer_name: str = Form(...),
    customer_email: str = Form(...),
    customer_phone: str = Form(...),
    service: str = Form(...),
    booking_date: str = Form(...),
    booking_time: str = Form(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db)
):
    owner = crud.get_owner_by_slug(db, owner_slug)
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")

    try:
        booking_datetime_str = f"{booking_date} {booking_time}"
        booking_datetime = datetime.strptime(booking_datetime_str, "%Y-%m-%d %H:%M")
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

    background_tasks.add_task(
        notifications.send_email_confirmation, 
        to_email=customer_email, 
        subject="Booking Confirmation", 
        body=f"Hi {customer_name}, your booking for {service} on {booking_datetime} is confirmed with {owner.business_name}."
    )
    background_tasks.add_task(
        notifications.send_whatsapp_notification,
        to_phone=owner.phone, 
        message=f"New booking for {service} on {booking_datetime} by {customer_name} ({customer_phone})."
    )

    templates = request.state.templates
    return templates.TemplateResponse("booking_confirmation.html", {
        "request": request,
        "booking": db_booking,
        "owner": owner,
        "lang": request.state.locale
    })
