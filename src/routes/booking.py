from fastapi import APIRouter, Request, Depends, Form, BackgroundTasks, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from pydantic import ValidationError
from datetime import datetime
import logging

from .. import crud, models, schemas, database, notifications
import os

router = APIRouter()
logger = logging.getLogger(__name__)

# Dependency to get DB session
def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/{owner_slug}", response_class=HTMLResponse)
async def get_booking_page(request: Request, owner_slug: str, db: Session = Depends(get_db)):
    templates_env = request.state.templates.env # Use the env from middleware

    owner = crud.get_owner_by_slug(db, owner_slug)
    if not owner:
        raise HTTPException(status_code=404, detail=templates_env.gettext("Owner not found"))

    owner_services = [schemas.ServiceSchema(**s) for s in owner.services_json] if owner.services_json else []
    owner_availability = owner.availability_json if owner.availability_json else {}

    return templates_env.TemplateResponse("booking_page.html", {
        "request": request,
        "owner": owner,
        "services": owner_services,
        "availability": owner_availability,
        "lang": request.state.locale # Use request.state.locale
    })

@router.post("/{owner_slug}/submit", response_class=HTMLResponse)
async def submit_booking(
    request: Request,
    owner_slug: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    customer_name: str = Form(...),
    customer_email: str = Form(...),
    customer_phone: str = Form(None),
    service_id: int = Form(...),
    booking_date: str = Form(...),
    booking_time: str = Form(...)
):
    templates_env = request.state.templates.env # Use the env from middleware

    owner = crud.get_owner_by_slug(db, owner_slug)
    if not owner:
        raise HTTPException(status_code=404, detail=templates_env.gettext("Owner not found"))

    # Find the selected service
    selected_service = next((s for s in owner.services_json if s.get("id") == service_id), None)
    if not selected_service:
        # Re-render booking page with error
        return templates_env.TemplateResponse("booking_page.html", {
            "request": request,
            "owner": owner,
            "services": [schemas.ServiceSchema(**s) for s in owner.services_json] if owner.services_json else [],
            "availability": owner.availability_json if owner.availability_json else {},
            "lang": request.state.locale,
            "error_message": templates_env.gettext("Selected service is invalid.")
        }, status_code=400)

    try:
        # Combine date and time
        booking_datetime_str = f"{booking_date} {booking_time}"
        booking_dt = datetime.strptime(booking_datetime_str, '%Y-%m-%d %H:%M')

        # Basic availability check (more complex logic might be needed here)
        # For MVP, assume any selected slot from the UI is valid for now.

        booking_schema = schemas.BookingCreate(
            customer_name=customer_name,
            customer_email=customer_email,
            customer_phone=customer_phone,
            service_name=selected_service["name"],
            datetime=booking_dt
        )

        db_booking = crud.create_booking(db, booking_schema, owner.id)

        # Send notifications in background
        background_tasks.add_task(
            notifications.send_booking_confirmation_email,
            customer_email,
            owner.name,
            selected_service["name"],
            booking_dt,
            customer_name
        )
        background_tasks.add_task(
            notifications.send_owner_booking_notification_email,
            owner.email,
            customer_name,
            customer_phone,
            selected_service["name"],
            booking_dt
        )
        if owner.phone: # Only send WhatsApp if owner has provided a phone number
            background_tasks.add_task(
                notifications.send_owner_booking_notification_whatsapp,
                owner.phone,
                customer_name,
                customer_email,
                selected_service["name"],
                booking_dt
            )

        # Redirect to avoid form resubmission on refresh
        response = RedirectResponse(url=f"/book/{owner_slug}/confirmation?lang={request.state.locale}", status_code=303)
        return response

    except ValidationError as e:
        logger.error(f"Validation error during booking submission: {e.errors()}")
        return templates_env.TemplateResponse("booking_page.html", {
            "request": request,
            "owner": owner,
            "services": [schemas.ServiceSchema(**s) for s in owner.services_json] if owner.services_json else [],
            "availability": owner.availability_json if owner.availability_json else {},
            "lang": request.state.locale,
            "error_message": templates_env.gettext(f"Invalid input: {e.errors()}") # Display error details
        }, status_code=400)
    except ValueError as e: # For datetime parsing errors
        logger.error(f"ValueError during booking submission: {e}")
        return templates_env.TemplateResponse("booking_page.html", {
            "request": request,
            "owner": owner,
            "services": [schemas.ServiceSchema(**s) for s in owner.services_json] if owner.services_json else [],
            "availability": owner.availability_json if owner.availability_json else {},
            "lang": request.state.locale,
            "error_message": templates_env.gettext(f"Invalid date or time format. Please select a valid date and time.") # Generic error for user
        }, status_code=400)
    except SQLAlchemyError as e:
        logger.exception(f"Database error during booking submission: {e}")
        db.rollback()
        return templates_env.TemplateResponse("booking_page.html", {
            "request": request,
            "owner": owner,
            "services": [schemas.ServiceSchema(**s) for s in owner.services_json] if owner.services_json else [],
            "availability": owner.availability_json if owner.availability_json else {},
            "lang": request.state.locale,
            "error_message": templates_env.gettext("A database error occurred while processing your booking. Please try again.")
        }, status_code=500)
    except Exception as e:
        logger.exception(f"Unexpected error during booking submission: {e}")
        return templates_env.TemplateResponse("booking_page.html", {
            "request": request,
            "owner": owner,
            "services": [schemas.ServiceSchema(**s) for s in owner.services_json] if owner.services_json else [],
            "availability": owner.availability_json if owner.availability_json else {},
            "lang": request.state.locale,
            "error_message": templates_env.gettext("An unexpected error occurred. Please try again.")
        }, status_code=500)

@router.get("/{owner_slug}/confirmation", response_class=HTMLResponse)
async def booking_confirmation_page(request: Request, owner_slug: str, db: Session = Depends(get_db)):
    templates_env = request.state.templates.env
    owner = crud.get_owner_by_slug(db, owner_slug)
    if not owner:
        raise HTTPException(status_code=404, detail=templates_env.gettext("Owner not found"))

    return templates_env.TemplateResponse("booking_confirmation.html", {
        "request": request,
        "owner": owner,
        "lang": request.state.locale,
        "message": templates_env.gettext("Your booking has been successfully submitted!")
    })