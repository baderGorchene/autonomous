from fastapi import APIRouter, Request, Depends, Form, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from pydantic import ValidationError
from datetime import datetime, date
from typing import Optional
import logging

from .. import crud, schemas, database, notifications, models

router = APIRouter()

logger = logging.getLogger(__name__)

def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/{owner_slug}")
def get_booking_page(request: Request, owner_slug: str, db: Session = Depends(get_db)):
    owner = crud.get_owner_by_slug(db, owner_slug)
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")
    
    owner_services = [schemas.ServiceSchema(**s) for s in owner.services_json] if owner.services_json else []
    
    today_str = date.today().isoformat()

    return request.state.templates.TemplateResponse("booking_page.html", {
        "request": request,
        "owner": owner,
        "services": owner_services,
        "lang": request.state.locale,
        "today_str": today_str,
        "error_message": None,
        "form_data": {}
    })

@router.post("/{owner_slug}")
async def submit_booking(
    request: Request,
    owner_slug: str,
    background_tasks: BackgroundTasks,
    service_name: str = Form(...),
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

    owner_services = [schemas.ServiceSchema(**s) for s in owner.services_json] if owner.services_json else []
    selected_service = next((s for s in owner_services if s.name == service_name), None)

    if not selected_service:
        error_message = request.state.templates.env.gettext("Selected service is invalid.")
        return request.state.templates.TemplateResponse("booking_page.html", {
            "request": request,
            "owner": owner,
            "services": owner_services,
            "lang": request.state.locale,
            "today_str": date.today().isoformat(),
            "error_message": error_message,
            "form_data": {"service_name": service_name, "date": date, "time": time, "customer_name": customer_name, "customer_email": customer_email, "customer_phone": customer_phone}
        }, status_code=400)

    try:
        booking_datetime = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
        
        booking_data = schemas.BookingCreate(
            service_name=service_name,
            datetime=booking_datetime,
            customer_name=customer_name,
            customer_email=customer_email,
            customer_phone=customer_phone,
            owner_id=owner.id
        )
        
        db_booking = crud.create_booking(db=db, booking=booking_data, owner_id=owner.id)

        background_tasks.add_task(
            notifications.send_booking_confirmation,
            owner_email=owner.email,
            owner_phone=owner.phone,
            customer_email=customer_email,
            customer_phone=customer_phone,
            booking=db_booking,
            owner_name=owner.name,
            business_name=owner.business_name
        )
        
        return request.state.templates.TemplateResponse("booking_confirmation.html", {
            "request": request,
            "booking": db_booking,
            "owner": owner,
            "lang": request.state.locale
        })

    except ValidationError as e:
        logger.error(f"Validation error during booking submission: {e.errors()}")
        error_message = request.state.templates.env.gettext(f"Invalid input for booking: {e.errors()}")
    except SQLAlchemyError as e:
        logger.exception(f"Database error during booking submission: {e}")
        db.rollback()
        error_message = request.state.templates.env.gettext("A database error occurred while processing your booking. Please try again.")
    except Exception as e:
        logger.exception(f"Unexpected error during booking submission: {e}")
        error_message = request.state.templates.env.gettext("An unexpected error occurred. Please try again.")
    
    return request.state.templates.TemplateResponse("booking_page.html", {
        "request": request,
        "owner": owner,
        "services": owner_services,
        "lang": request.state.locale,
        "today_str": date.today().isoformat(),
        "error_message": error_message,
        "form_data": {"service_name": service_name, "date": date, "time": time, "customer_name": customer_name, "customer_email": customer_email, "customer_phone": customer_phone}
    }, status_code=400)
