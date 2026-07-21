from fastapi import APIRouter, Request, Depends, Form, BackgroundTasks, HTTPException
from sqlalchemy.orm import Session
from .. import models, schemas, database, notifications, crud
from datetime import datetime
from typing import Optional

router = APIRouter()

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
    
    # Pass the request.state.templates and request.state.locale to the template
    return request.state.templates.TemplateResponse("booking_page.html", {
        "request": request,
        "owner": owner,
        "lang": request.state.locale # Pass language to template
    })

@router.post("/{owner_slug}")
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

    # Send notifications in the background
    background_tasks.add_task(notifications.send_owner_notification, owner, db_booking)
    background_tasks.add_task(notifications.send_customer_confirmation, owner, db_booking)

    # Render booking confirmation page
    return request.state.templates.TemplateResponse("booking_confirmation.html", {
        "request": request,
        "owner": owner,
        "booking": db_booking,
        "lang": request.state.locale # Pass language to confirmation template as well
    })
