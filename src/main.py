from fastapi import FastAPI, Depends, HTTPException, status, Request, Form, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
import json
import datetime
import logging
from urllib.parse import urlencode

from . import crud, models, schemas, security, notifications
from .database import SessionLocal, engine, create_tables, get_db
from .config import settings
from .i18n_config import get_jinja_env
import gettext
import os

# Create tables on startup (only for development/testing, migrations for production)
create_tables()

app = FastAPI()

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Middleware for language detection and setting
@app.middleware("http")
async def add_language_middleware(request: Request, call_next):
    lang = request.query_params.get("lang", "en")
    request.state.lang = lang
    response = await call_next(request)
    return response

# Dependency for Jinja2 environment with i18n
def get_jinja_env_dependency(request: Request):
    return get_jinja_env(request.state.lang)

# Health check endpoint
@app.get("/health", response_model=schemas.Message)
def health_check():
    return {"message": "ok"}

# --- Owner Authentication and Profile Management ---

@app.post("/owner/signup", response_model=schemas.Token)
def signup_owner(owner: schemas.OwnerCreate, db: Session = Depends(get_db)):
    db_owner = crud.get_owner_by_email(db, email=owner.email)
    if db_owner:
        raise HTTPException(status_code=400, detail="Email already registered")
    db_owner_by_slug = crud.get_owner_by_slug(db, slug=owner.slug)
    if db_owner_by_slug:
        raise HTTPException(status_code=400, detail="Business slug already taken")
    
    db_owner = crud.create_owner(db=db, owner=owner)
    access_token = security.create_access_token(data={"sub": db_owner.email})
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/owner/token", response_model=schemas.Token)
def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    owner = crud.authenticate_owner(db, form_data.username, form_data.password)
    if not owner:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = security.create_access_token(data={"sub": owner.email})
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/owner/me", response_model=schemas.Owner)
def read_owner_me(current_owner: models.Owner = Depends(security.get_current_owner)):
    return current_owner

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(
    request: Request,
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(security.get_current_owner),
    env: Any = Depends(get_jinja_env_dependency)
):
    _ = env.get_template('dashboard.html').globals['gettext'] # Initialize gettext for the template
    
    owner_data = schemas.Owner.from_orm(current_owner).dict()
    owner_data['services'] = json.loads(current_owner.services_json) if current_owner.services_json else []
    owner_data['availability'] = json.loads(current_owner.availability_json) if current_owner.availability_json else {}

    upcoming_bookings = crud.get_owner_bookings(db, owner_id=current_owner.id)

    # Convert booking_date from datetime to string for JSON serialization if needed, or format for display
    for booking in upcoming_bookings:
        booking.booking_date_str = booking.booking_date.strftime("%Y-%m-%d")

    return env.get_template("dashboard.html").render(
        request=request,
        owner=owner_data,
        bookings=upcoming_bookings,
        current_lang=request.state.lang
    )

@app.post("/owner/profile", response_class=RedirectResponse, status_code=status.HTTP_303_SEE_OTHER)
async def update_owner_profile(
    request: Request,
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(security.get_current_owner),
    name: str = Form(...),
    business_name: str = Form(...),
    phone: Optional[str] = Form(None),
    services_json: str = Form("[]"),
    availability_json: str = Form("{}")
):
    try:
        # Validate JSON inputs
        services_data = json.loads(services_json)
        availability_data = json.loads(availability_json)

        # Basic validation for services and availability schemas
        # This is a simplified check; more robust validation would iterate and validate each item
        for service in services_data:
            schemas.Service(**service) # Will raise ValidationError if invalid
        for day, slots in availability_data.items():
            for slot in slots:
                schemas.AvailabilitySlot(**slot) # Will raise ValidationError if invalid

        owner_update = schemas.OwnerProfileUpdate(
            name=name,
            business_name=business_name,
            phone=phone,
            services=services_data,
            availability=availability_data
        )

        current_owner.name = owner_update.name
        current_owner.business_name = owner_update.business_name
        current_owner.phone = owner_update.phone
        current_owner.services_json = json.dumps(owner_update.services)
        current_owner.availability_json = json.dumps(owner_update.availability)

        db.add(current_owner)
        db.commit()
        db.refresh(current_owner)
        
        return RedirectResponse(url=f"/dashboard?lang={request.state.lang}", status_code=status.HTTP_303_SEE_OTHER)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON format for services or availability.")
    except Exception as e:
        logger.error(f"Error updating owner profile: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update profile: {e}")


# --- Public Booking Page ---

@app.get("/{owner_slug}", response_class=HTMLResponse)
async def public_booking_page(
    owner_slug: str,
    request: Request,
    db: Session = Depends(get_db),
    env: Any = Depends(get_jinja_env_dependency)
):
    _ = env.get_template('booking_page.html').globals['gettext'] # Initialize gettext for the template
    owner = crud.get_owner_by_slug(db, slug=owner_slug)
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")

    services = json.loads(owner.services_json) if owner.services_json else []
    availability = json.loads(owner.availability_json) if owner.availability_json else {}

    return env.get_template("booking_page.html").render(
        request=request,
        owner=owner,
        services=services,
        availability=availability,
        current_lang=request.state.lang
    )

@app.post("/{owner_slug}/book", response_class=HTMLResponse)
async def submit_booking(
    owner_slug: str,
    request: Request,
    db: Session = Depends(get_db),
    env: Any = Depends(get_jinja_env_dependency),
    customer_name: str = Form(...),
    customer_email: EmailStr = Form(...),
    customer_phone: Optional[str] = Form(None),
    service_name: str = Form(...),
    booking_date: str = Form(...), # YYYY-MM-DD
    booking_time: str = Form(...)  # HH:MM
):
    _ = env.get_template('booking_confirmation.html').globals['gettext'] # Initialize gettext for the template
    owner = crud.get_owner_by_slug(db, slug=owner_slug)
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")

    try:
        parsed_date = datetime.datetime.strptime(booking_date, "%Y-%m-%d").date()
        
        # Basic availability check (can be expanded)
        owner_availability = json.loads(owner.availability_json) if owner.availability_json else {}
        day_of_week = parsed_date.strftime("%A") # e.g., "Monday"
        
        is_available = False
        if day_of_week in owner_availability:
            for slot in owner_availability[day_of_week]:
                start_dt = datetime.datetime.strptime(f"{booking_date} {slot['start_time']}", "%Y-%m-%d %H:%M")
                end_dt = datetime.datetime.strptime(f"{booking_date} {slot['end_time']}", "%Y-%m-%d %H:%M")
                booking_dt = datetime.datetime.strptime(f"{booking_date} {booking_time}", "%Y-%m-%d %H:%M")

                if start_dt <= booking_dt < end_dt:
                    is_available = True
                    break
        
        if not is_available:
            # Render booking page again with an error message
            services = json.loads(owner.services_json) if owner.services_json else []
            availability = json.loads(owner.availability_json) if owner.availability_json else {}
            return env.get_template("booking_page.html").render(
                request=request,
                owner=owner,
                services=services,
                availability=availability,
                current_lang=request.state.lang,
                error_message=_("Selected time slot is not available or outside business hours.")
            )

        booking_data = schemas.BookingCreate(
            customer_name=customer_name,
            customer_email=customer_email,
            customer_phone=customer_phone,
            service_name=service_name,
            booking_date=parsed_date,
            booking_time=booking_time
        )
        
        db_booking = crud.create_booking(db=db, booking=booking_data, owner_id=owner.id)

        # Send notifications
        # Owner notification
        owner_subject = _("New Booking Received!")
        owner_html_content = env.get_template("email/owner_booking_notification.html").render(
            booking=db_booking, owner=owner, current_lang=request.state.lang
        )
        notifications.send_email_notification(owner.email, owner_subject, owner_html_content)
        if owner.phone:
            owner_whatsapp_message = _(f"New booking for {service_name} on {booking_date} at {booking_time} by {customer_name}. Email: {customer_email}, Phone: {customer_phone}")
            notifications.send_whatsapp_notification(owner.phone, owner_whatsapp_message)

        # Customer confirmation
        customer_subject = _("Your Booking is Confirmed!")
        customer_html_content = env.get_template("email/customer_booking_confirmation.html").render(
            booking=db_booking, owner=owner, current_lang=request.state.lang
        )
        notifications.send_email_notification(customer_email, customer_subject, customer_html_content)
        if customer_phone:
            customer_whatsapp_message = _(f"Your booking for {service_name} with {owner.business_name} on {booking_date} at {booking_time} is confirmed.")
            notifications.send_whatsapp_notification(customer_phone, customer_whatsapp_message)

        return env.get_template("booking_confirmation.html").render(
            request=request,
            booking=db_booking,
            owner=owner,
            current_lang=request.state.lang,
            gettext=env.get_template('booking_confirmation.html').globals['gettext'] # Pass gettext explicitly
        )

    except ValueError as ve:
        # Handle date/time parsing errors
        services = json.loads(owner.services_json) if owner.services_json else []
        availability = json.loads(owner.availability_json) if owner.availability_json else {}
        return env.get_template("booking_page.html").render(
            request=request,
            owner=owner,
            services=services,
            availability=availability,
            current_lang=request.state.lang,
            error_message=_("Invalid date or time format provided.")
        )
    except Exception as e:
        logger.error(f"Error processing booking: {e}")
        services = json.loads(owner.services_json) if owner.services_json else []
        availability = json.loads(owner.availability_json) if owner.availability_json else {}
        return env.get_template("booking_page.html").render(
            request=request,
            owner=owner,
            services=services,
            availability=availability,
            current_lang=request.state.lang,
            error_message=_("An unexpected error occurred during booking. Please try again.")
        )

# --- Language Toggle Redirect ---
@app.get("/set_language/{lang_code}", response_class=RedirectResponse)
async def set_language(request: Request, lang_code: str):
    referer = request.headers.get("referer")
    if referer:
        # Parse the referer URL and update the 'lang' query parameter
        from urllib.parse import urlparse, urlunparse, parse_qs, urlencode
        parsed_url = urlparse(referer)
        query_params = parse_qs(parsed_url.query)
        query_params['lang'] = [lang_code]
        new_query = urlencode(query_params, doseq=True)
        new_url = urlunparse(parsed_url._replace(query=new_query))
        return RedirectResponse(url=new_url, status_code=status.HTTP_302_FOUND)
    return RedirectResponse(url=f"/?lang={lang_code}", status_code=status.HTTP_302_FOUND)
