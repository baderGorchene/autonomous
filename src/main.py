from fastapi import FastAPI, Depends, HTTPException, status, Request, Response, Form, Path
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from src.database import SessionLocal, engine, create_tables, get_db, drop_tables # Import drop_tables
from src import models, schemas, crud, security, dependencies, notifications
from src.config import settings
from datetime import timedelta, date, datetime
import json
import logging
from typing import Optional, List
from src.i18n_config import get_jinja_templates, get_templates_env # Import get_templates_env
from pydantic import ValidationError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
import gettext # For explicit gettext usage if needed
from babel.dates import format_date, format_time # For localized date/time formatting

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Drop and create tables for a clean start during development/testing.
# In production, you'd use migrations.
if settings.TESTING:
    drop_tables()
create_tables()

app = FastAPI()

# Middleware to set language based on query parameter or Accept-Language header
class LanguageMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        lang = request.query_params.get("lang", "en") # Default to English
        if lang not in ["en", "ar", "fr"]: # Supported languages
            lang = "en"
        request.state.lang = lang
        response = await call_next(request)
        return response

app.add_middleware(LanguageMiddleware)

# Root path redirects to signup
@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request, templates: Jinja2Templates = Depends(get_templates_env)):
    return RedirectResponse(url="/signup", status_code=status.HTTP_302_FOUND)

# Health check endpoint
@app.get("/health")
async def health_check():
    return {"status": "ok"}

# Owner Signup
@app.get("/signup", response_class=HTMLResponse)
async def signup_form(request: Request, templates: Jinja2Templates = Depends(get_templates_env)):
    return templates.TemplateResponse("signup.html", {"request": request, "error": None})

@app.post("/signup", response_class=HTMLResponse)
async def signup_owner(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    business_name: str = Form(...),
    slug: str = Form(...),
    phone: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    templates: Jinja2Templates = Depends(get_templates_env)
):
    try:
        owner_data = schemas.OwnerCreate(
            name=name, email=email, password=password,
            business_name=business_name, slug=slug, phone=phone
        )
    except ValidationError as e:
        return templates.TemplateResponse("signup.html", {"request": request, "error": f"Invalid input: {e}"})

    db_owner = crud.get_owner_by_email(db, email=owner_data.email)
    if db_owner:
        return templates.TemplateResponse("signup.html", {"request": request, "error": "Email already registered."})
    db_owner = crud.get_owner_by_slug(db, slug=owner_data.slug)
    if db_owner:
        return templates.TemplateResponse("signup.html", {"request": request, "error": "Business URL already taken."})

    crud.create_owner(db=db, owner=owner_data)
    return RedirectResponse(url="/login?lang=" + request.state.lang, status_code=status.HTTP_302_FOUND)

# Owner Login
@app.get("/login", response_class=HTMLResponse)
async def login_form(request: Request, templates: Jinja2Templates = Depends(get_templates_env)):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})

@app.post("/token", response_model=schemas.Token)
async def login_for_access_token(
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    owner = crud.authenticate_owner(db, form_data.username, form_data.password)
    if not owner:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": owner.email}, expires_delta=access_token_expires
    )
    # Set the token in a cookie
    response.set_cookie(key="access_token", value=access_token, httponly=True, max_age=access_token_expires.total_seconds())
    return {"access_token": access_token, "token_type": "bearer"}

# Owner Dashboard
@app.get("/dashboard", response_class=HTMLResponse)
async def owner_dashboard(
    request: Request,
    current_owner: schemas.Owner = Depends(dependencies.get_current_owner),
    db: Session = Depends(get_db),
    templates: Jinja2Templates = Depends(get_templates_env)
):
    bookings = crud.get_owner_bookings(db, owner_id=current_owner.id)
    # Convert booking_date to localized string for display
    locale = request.state.lang
    for booking in bookings:
        booking.display_date = format_date(booking.booking_date, format='full', locale=locale)
        booking.display_time = format_time(booking.booking_time, format='short', locale=locale) # Assuming booking_time is parseable by Babel
    return templates.TemplateResponse("dashboard.html", {"request": request, "owner": current_owner, "bookings": bookings, "error": None})

@app.post("/dashboard/update_profile", response_class=HTMLResponse)
async def update_owner_profile(
    request: Request,
    name: str = Form(...),
    business_name: str = Form(...),
    phone: Optional[str] = Form(None),
    current_owner: models.Owner = Depends(dependencies.get_current_owner),
    db: Session = Depends(get_db),
    templates: Jinja2Templates = Depends(get_templates_env)
):
    try:
        owner_update = schemas.OwnerProfileUpdate(name=name, business_name=business_name, phone=phone)
        updated_owner = crud.update_owner_profile(db, current_owner, owner_update)
        # Refresh current_owner data
        request.state.current_owner = updated_owner
        bookings = crud.get_owner_bookings(db, owner_id=updated_owner.id)
        locale = request.state.lang
        for booking in bookings:
            booking.display_date = format_date(booking.booking_date, format='full', locale=locale)
            booking.display_time = format_time(booking.booking_time, format='short', locale=locale)
        return templates.TemplateResponse("dashboard.html", {"request": request, "owner": updated_owner, "bookings": bookings, "success": "Profile updated successfully!", "error": None})
    except ValidationError as e:
        bookings = crud.get_owner_bookings(db, owner_id=current_owner.id)
        locale = request.state.lang
        for booking in bookings:
            booking.display_date = format_date(booking.booking_date, format='full', locale=locale)
            booking.display_time = format_time(booking.booking_time, format='short', locale=locale)
        return templates.TemplateResponse("dashboard.html", {"request": request, "owner": current_owner, "bookings": bookings, "error": f"Validation error: {e}"})
    except Exception as e:
        logger.error(f"Error updating profile: {e}")
        bookings = crud.get_owner_bookings(db, owner_id=current_owner.id)
        locale = request.state.lang
        for booking in bookings:
            booking.display_date = format_date(booking.booking_date, format='full', locale=locale)
            booking.display_time = format_time(booking.booking_time, format='short', locale=locale)
        return templates.TemplateResponse("dashboard.html", {"request": request, "owner": current_owner, "bookings": bookings, "error": "An unexpected error occurred."})


# Public Booking Page
@app.get("/book/{owner_slug}", response_class=HTMLResponse)
async def public_booking_page(
    request: Request,
    owner_slug: str = Path(..., regex=r"^[a-z0-9-]+"),
    db: Session = Depends(get_db),
    templates: Jinja2Templates = Depends(get_templates_env)
):
    owner = crud.get_owner_by_slug(db, slug=owner_slug)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking page not found")

    services = json.loads(owner.services_json) if owner.services_json else []
    availability = json.loads(owner.availability_json) if owner.availability_json else {}

    # Dummy data for now, actual implementation would calculate available slots
    # For testing, just provide some mock availability or a default service price
    mock_service_price = 50.00 # Example price for currency filter test

    return templates.TemplateResponse("booking_page.html", {
        "request": request,
        "owner": owner,
        "services": services,
        "availability": availability,
        "mock_service_price": mock_service_price, # Pass mock price for testing currency filter
        "error": None
    })

@app.post("/book/{owner_slug}", response_class=HTMLResponse)
async def submit_booking(
    request: Request,
    owner_slug: str = Path(..., regex=r"^[a-z0-9-]+"),
    customer_name: str = Form(...),
    customer_email: str = Form(...),
    customer_phone: Optional[str] = Form(None),
    service_name: str = Form(...),
    booking_date: str = Form(...), # YYYY-MM-DD
    booking_time: str = Form(...), # HH:MM AM/PM
    db: Session = Depends(get_db),
    templates: Jinja2Templates = Depends(get_templates_env)
):
    owner = crud.get_owner_by_slug(db, slug=owner_slug)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking page not found")

    try:
        booking_date_obj = datetime.strptime(booking_date, "%Y-%m-%d").date()
        # Basic validation: booking date must be today or in the future
        if booking_date_obj < date.today():
            raise ValueError("Booking date cannot be in the past.")

        booking_data = schemas.BookingCreate(
            customer_name=customer_name,
            customer_email=customer_email,
            customer_phone=customer_phone,
            service_name=service_name,
            booking_date=booking_date_obj,
            booking_time=booking_time
        )
        db_booking = crud.create_booking(db=db, booking=booking_data, owner_id=owner.id)

        # Send notifications
        notifications.send_email_confirmation_to_customer(
            customer_email=booking_data.customer_email,
            owner_name=owner.name,
            service_name=booking_data.service_name,
            booking_date=booking_data.booking_date.strftime("%Y-%m-%d"),
            booking_time=booking_data.booking_time,
            owner_email=owner.email
        )
        notifications.send_email_notification_to_owner(
            owner_email=owner.email,
            customer_name=booking_data.customer_name,
            customer_email=booking_data.customer_email,
            service_name=booking_data.service_name,
            booking_date=booking_data.booking_date.strftime("%Y-%m-%d"),
            booking_time=booking_data.booking_time,
            owner_name=owner.name
        )
        if owner.phone:
            notifications.send_whatsapp_notification_to_owner(
                owner_phone=owner.phone,
                customer_name=booking_data.customer_name,
                service_name=booking_data.service_name,
                booking_date=booking_data.booking_date.strftime("%Y-%m-%d"),
                booking_time=booking_data.booking_time
            )

        return templates.TemplateResponse("booking_confirmation.html", {
            "request": request,
            "booking": db_booking,
            "owner": owner
        })

    except ValidationError as e:
        services = json.loads(owner.services_json) if owner.services_json else []
        availability = json.loads(owner.availability_json) if owner.availability_json else {}
        mock_service_price = 50.00
        return templates.TemplateResponse("booking_page.html", {
            "request": request, "owner": owner, "services": services,
            "availability": availability, "mock_service_price": mock_service_price,
            "error": f"Invalid booking details: {e}"
        })
    except ValueError as e:
        services = json.loads(owner.services_json) if owner.services_json else []
        availability = json.loads(owner.availability_json) if owner.availability_json else {}
        mock_service_price = 50.00
        return templates.TemplateResponse("booking_page.html", {
            "request": request, "owner": owner, "services": services,
            "availability": availability, "mock_service_price": mock_service_price,
            "error": f"Booking error: {e}"
        })
    except Exception as e:
        logger.error(f"Error submitting booking: {e}")
        services = json.loads(owner.services_json) if owner.services_json else []
        availability = json.loads(owner.availability_json) if owner.availability_json else {}
        mock_service_price = 50.00
        return templates.TemplateResponse("booking_page.html", {
            "request": request, "owner": owner, "services": services,
            "availability": availability, "mock_service_price": mock_service_price,
            "error": "An unexpected error occurred during booking."
        })