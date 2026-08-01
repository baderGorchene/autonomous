import json
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, Depends, HTTPException, status, Request, Form, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware
from starlette.staticfiles import StaticFiles

from . import crud, models, schemas, security, notifications
from .database import SessionLocal, engine, create_tables, get_db
from .config import settings
from .i18n_config import get_jinja_env
import gettext
import os
import re

# Initialize logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create database tables on startup
create_tables()

app = FastAPI()

# Add Session Middleware for language preference
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

# Static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Templates setup (initial for non-i18n routes or fallback)
templates = Jinja2Templates(directory="templates")

# Helper to get Jinja2 environment with correct locale
def get_templates(request: Request):
    locale = request.session.get('locale', 'en')
    return get_jinja_env(locale)

@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "ok", "message": "BookSlot API is running!"}

# --- Authentication and Owner Management ---
@app.post("/token", response_model=schemas.Token, tags=["Authentication"])
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)
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
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/signup", response_class=HTMLResponse, tags=["Authentication"])
async def signup_page(request: Request, templates: Jinja2Templates = Depends(get_templates)):
    return templates.TemplateResponse("signup.html", {"request": request})

@app.post("/signup", response_class=HTMLResponse, tags=["Authentication"])
async def create_owner_signup(
    request: Request,
    templates: Jinja2Templates = Depends(get_templates),
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    business_name: str = Form(...),
    slug: str = Form(...),
    phone: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    _ = templates.get_global('_')
    db_owner = crud.get_owner_by_email(db, email=email)
    if db_owner:
        return templates.TemplateResponse(
            "signup.html",
            {"request": request, "error": _("Email already registered")},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    db_owner = crud.get_owner_by_slug(db, slug=slug)
    if db_owner:
        return templates.TemplateResponse(
            "signup.html",
            {"request": request, "error": _("Business URL already taken")},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    owner = schemas.OwnerCreate(
        name=name, email=email, password=password, business_name=business_name, slug=slug, phone=phone
    )
    crud.create_owner(db=db, owner=owner)
    # Redirect to login page after successful signup
    response = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    return response

@app.get("/login", response_class=HTMLResponse, tags=["Authentication"])
async def login_page(request: Request, templates: Jinja2Templates = Depends(get_templates)):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login", response_class=HTMLResponse, tags=["Authentication"])
async def login(
    request: Request,
    templates: Jinja2Templates = Depends(get_templates),
    username: str = Form(..., alias="email"), # Use email for username
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    _ = templates.get_global('_')
    owner = crud.authenticate_owner(db, username, password)
    if not owner:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": _("Incorrect email or password")},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": owner.email}, expires_delta=access_token_expires
    )
    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    response.set_cookie(key="access_token", value=access_token, httponly=True, samesite="Lax")
    return response

@app.get("/logout", tags=["Authentication"])
async def logout(request: Request):
    response = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    response.delete_cookie(key="access_token")
    return response

# --- Dashboard and Profile Management ---
@app.get("/dashboard", response_class=HTMLResponse, tags=["Dashboard"])
async def dashboard(
    request: Request,
    templates: Jinja2Templates = Depends(get_templates),
    current_owner: models.Owner = Depends(security.get_current_owner),
    db: Session = Depends(get_db),
):
    _ = templates.get_global('_')
    bookings = crud.get_owner_bookings(db, current_owner.id)
    
    # Parse services and availability
    services = json.loads(current_owner.services_json) if current_owner.services_json else []
    availability = json.loads(current_owner.availability_json) if current_owner.availability_json else {}

    # Convert booking_date and booking_time to datetime objects for sorting and display
    for booking in bookings:
        try:
            booking.display_datetime = datetime.strptime(f"{booking.booking_date} {booking.booking_time}", "%Y-%m-%d %H:%M")
        except ValueError:
            booking.display_datetime = None # Handle malformed dates gracefully

    # Filter upcoming bookings
    now = datetime.now()
    upcoming_bookings = [b for b in bookings if b.display_datetime and b.display_datetime >= now]
    upcoming_bookings.sort(key=lambda b: b.display_datetime) # Sort by date and time

    # Prepare availability for display in a structured way (e.g., list of dicts for form)
    # This might need to be more sophisticated depending on frontend needs
    availability_list = []
    for day, slots in availability.items():
        for slot in slots:
            availability_list.append({"day_of_week": day, "start_time": slot['start_time'], "end_time": slot['end_time']})

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "owner": current_owner,
            "bookings": upcoming_bookings,
            "services": services,
            "availability": availability_list,
            "today": datetime.now().strftime("%Y-%m-%d") # For date input default
        },
    )

@app.post("/dashboard/update_profile", response_class=HTMLResponse, tags=["Dashboard"])
async def update_owner_profile(
    request: Request,
    templates: Jinja2Templates = Depends(get_templates),
    name: str = Form(...),
    business_name: str = Form(...),
    phone: Optional[str] = Form(None),
    services_json: str = Form(..., alias="services"), # Expecting a JSON string
    availability_json: str = Form(..., alias="availability"), # Expecting a JSON string
    current_owner: models.Owner = Depends(security.get_current_owner),
    db: Session = Depends(get_db),
):
    _ = templates.get_global('_')
    try:
        # Parse and validate services
        parsed_services = json.loads(services_json)
        validated_services = []
        for service_data in parsed_services:
            # Basic validation, more robust validation could use Pydantic directly
            if not isinstance(service_data, dict) or not all(k in service_data for k in ['name', 'duration', 'price']):
                raise ValueError(_("Invalid service data format."))
            validated_services.append(schemas.Service(**service_data).dict())

        # Parse and validate availability
        parsed_availability = json.loads(availability_json)
        validated_availability = {}
        for day, slots in parsed_availability.items():
            if not isinstance(slots, list):
                raise ValueError(_("Invalid availability data format for day") + f" {day}.")
            validated_slots = []
            for slot_data in slots:
                if not isinstance(slot_data, dict) or not all(k in slot_data for k in ['start_time', 'end_time']):
                    raise ValueError(_("Invalid slot data format for day") + f" {day}.")
                # Further time format validation could be added
                validated_slots.append({"start_time": slot_data['start_time'], "end_time": slot_data['end_time']})
            validated_availability[day] = validated_slots

        owner_update = schemas.OwnerProfileUpdate(
            name=name,
            business_name=business_name,
            phone=phone,
            services=validated_services,
            availability=validated_availability
        )

        current_owner.name = owner_update.name
        current_owner.business_name = owner_update.business_name
        current_owner.phone = owner_update.phone
        current_owner.services_json = json.dumps(owner_update.services)
        current_owner.availability_json = json.dumps(owner_update.availability)

        db.add(current_owner)
        db.commit()
        db.refresh(current_owner)

        response = RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
        response.headers["X-Message"] = _("Profile updated successfully!")
        return response

    except json.JSONDecodeError:
        return templates.TemplateResponse(
            "dashboard.html",
            {"request": request, "owner": current_owner, "error": _("Invalid JSON format for services or availability.")},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    except ValueError as e:
        return templates.TemplateResponse(
            "dashboard.html",
            {"request": request, "owner": current_owner, "error": str(e)},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    except Exception as e:
        logger.error(f"Error updating owner profile: {e}")
        return templates.TemplateResponse(
            "dashboard.html",
            {"request": request, "owner": current_owner, "error": _("An unexpected error occurred.")},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

# --- Public Booking Page ---
@app.get("/{owner_slug}", response_class=HTMLResponse, tags=["Public Booking"])
async def public_booking_page(
    owner_slug: str,
    request: Request,
    templates: Jinja2Templates = Depends(get_templates),
    db: Session = Depends(get_db),
):
    _ = templates.get_global('_')
    owner = crud.get_owner_by_slug(db, slug=owner_slug)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Owner not found"))

    services = json.loads(owner.services_json) if owner.services_json else []
    availability = json.loads(owner.availability_json) if owner.availability_json else {}

    return templates.TemplateResponse(
        "booking_page.html",
        {"request": request, "owner": owner, "services": services, "availability": availability, "owner_slug": owner_slug},
    )

@app.post("/{owner_slug}/book", response_class=HTMLResponse, tags=["Public Booking"])
async def submit_booking(
    owner_slug: str,
    request: Request,
    templates: Jinja2Templates = Depends(get_templates),
    customer_name: str = Form(...),
    customer_email: str = Form(...),
    customer_phone: Optional[str] = Form(None),
    service_name: str = Form(...),
    booking_date: str = Form(...),
    booking_time: str = Form(...),
    db: Session = Depends(get_db),
):
    _ = templates.get_global('_')
    owner = crud.get_owner_by_slug(db, slug=owner_slug)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Owner not found"))

    # Basic validation for date and time format
    try:
        selected_datetime = datetime.strptime(f"{booking_date} {booking_time}", "%Y-%m-%d %H:%M")
        if selected_datetime < datetime.now():
            return templates.TemplateResponse(
                "booking_page.html",
                {"request": request, "owner": owner, "error": _("Cannot book in the past."), "services": json.loads(owner.services_json) if owner.services_json else []},
                status_code=status.HTTP_400_BAD_REQUEST,
            )
    except ValueError:
        return templates.TemplateResponse(
            "booking_page.html",
            {"request": request, "owner": owner, "error": _("Invalid date or time format."), "services": json.loads(owner.services_json) if owner.services_json else []},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    # Validate if the chosen slot is available based on owner's availability
    availability = json.loads(owner.availability_json) if owner.availability_json else {}
    day_of_week = selected_datetime.strftime("%A") # e.g., "Monday"
    
    is_available = False
    if day_of_week in availability:
        for slot in availability[day_of_week]:
            # Create datetime objects for comparison (dummy date, only time matters here for slot check)
            slot_start_time = datetime.strptime(slot['start_time'], "%H:%M").time()
            slot_end_time = datetime.strptime(slot['end_time'], "%H:%M").time()
            booking_start_time = selected_datetime.time()
            
            # Check if booking time falls within an available slot
            if slot_start_time <= booking_start_time < slot_end_time:
                # Further check: ensure service duration fits within the slot.
                services = json.loads(owner.services_json) if owner.services_json else []
                selected_service = next((s for s in services if s['name'] == service_name), None)
                
                if selected_service:
                    service_duration = selected_service['duration'] # in minutes
                    booking_end_datetime = selected_datetime + timedelta(minutes=service_duration)
                    booking_end_time = booking_end_datetime.time()
                    
                    if booking_end_time <= slot_end_time:
                        is_available = True
                        break
    
    if not is_available:
        return templates.TemplateResponse(
            "booking_page.html",
            {"request": request, "owner": owner, "error": _("The selected time slot is not available or the service duration exceeds the slot."), "services": json.loads(owner.services_json) if owner.services_json else []},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    booking_data = schemas.BookingCreate(
        customer_name=customer_name,
        customer_email=customer_email,
        customer_phone=customer_phone,
        service_name=service_name,
        booking_date=booking_date,
        booking_time=booking_time,
    )

    try:
        db_booking = crud.create_booking(db=db, booking=booking_data, owner_id=owner.id)

        # Send notifications
        # Owner notification
        owner_subject = _("New Booking for your service!")
        owner_html_content = templates.TemplateResponse(
            "email_owner_notification.html",
            {"request": request, "booking": db_booking, "owner": owner},
            media_type="text/html"
        ).body.decode('utf-8')
        notifications.send_email(owner.email, owner_subject, owner_html_content)
        if owner.phone:
            owner_whatsapp_message = _("New booking received for {service_name} at {booking_time} on {booking_date} by {customer_name}. Check your dashboard for details.").format(
                service_name=db_booking.service_name,
                booking_time=db_booking.booking_time,
                booking_date=db_booking.booking_date,
                customer_name=db_booking.customer_name
            )
            notifications.send_whatsapp_message(owner.phone, owner_whatsapp_message)


        # Customer confirmation
        customer_subject = _("Your Booking Confirmation with {business_name}").format(business_name=owner.business_name)
        customer_html_content = templates.TemplateResponse(
            "email_customer_confirmation.html",
            {"request": request, "booking": db_booking, "owner": owner},
            media_type="text/html"
        ).body.decode('utf-8')
        notifications.send_email(customer_email, customer_subject, customer_html_content)
        if customer_phone:
            customer_whatsapp_message = _("Hi {customer_name}, your booking for {service_name} with {business_name} is confirmed for {booking_time} on {booking_date}. Thank you!").format(
                customer_name=db_booking.customer_name,
                service_name=db_booking.service_name,
                business_name=owner.business_name,
                booking_time=db_booking.booking_time,
                booking_date=db_booking.booking_date
            )
            notifications.send_whatsapp_message(customer_phone, customer_whatsapp_message)

        return templates.TemplateResponse(
            "booking_confirmation.html",
            {"request": request, "booking": db_booking, "owner": owner},
        )
    except Exception as e:
        logger.error(f"Error creating booking or sending notifications: {e}")
        return templates.TemplateResponse(
            "booking_page.html",
            {"request": request, "owner": owner, "error": _("An error occurred while processing your booking. Please try again."), "services": json.loads(owner.services_json) if owner.services_json else []},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

# --- Language Toggle ---
@app.get("/set_locale/{locale_code}", tags=["Internationalization"])
async def set_locale(locale_code: str, request: Request):
    if locale_code in ['en', 'ar', 'fr']: # Supported locales
        request.session['locale'] = locale_code
    
    # Redirect back to the referring page or to home if no referrer
    referrer = request.headers.get("Referer", "/")
    # Use regex to remove existing locale query param if present
    referrer = re.sub(r"([?&])locale=[^&]*", "", referrer)
    
    # Add new locale query param. Handle cases where there's already a query string.
    if "?" in referrer:
        redirect_url = f"{referrer}&locale={locale_code}"
    else:
        redirect_url = f"{referrer}?locale={locale_code}"
        
    return RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)

# --- Error Handlers ---
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    templates = get_jinja_env(request.session.get('locale', 'en'))
    _ = templates.get_global('_')
    
    if exc.status_code == status.HTTP_404_NOT_FOUND:
        return templates.TemplateResponse("404.html", {"request": request, "detail": _("Page not found.")}, status_code=status.HTTP_404_NOT_FOUND)
    
    return templates.TemplateResponse("error.html", {"request": request, "detail": exc.detail}, status_code=exc.status_code)

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    templates = get_jinja_env(request.session.get('locale', 'en'))
    _ = templates.get_global('_')
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return templates.TemplateResponse("error.html", {"request": request, "detail": _("An unexpected error occurred.")}, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
