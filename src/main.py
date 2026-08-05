from fastapi import FastAPI, Depends, HTTPException, status, Request, Form, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from . import crud, models, schemas, security, notifications, database, i18n
from .database import engine, get_db
from .dependencies import get_current_owner
from .config import settings
from datetime import datetime, timedelta
import json
import logging
from typing import Optional
from babel.dates import format_date, format_time, format_datetime, get_timezone
from babel.numbers import format_currency

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Create tables on startup
@app.on_event("startup")
def on_startup():
    database.create_tables()

# Jinja2 Templates setup
templates = Jinja2Templates(directory="templates")

# Add custom filter for i18n
@app.template_filter("i18n")
def i18n_filter(text: str, locale_code: Optional[str] = None):
    return i18n._(text, locale_code)

@app.template_filter("format_date")
def format_date_filter(date_str: str, locale_code: str = 'en'):
    try:
        dt_obj = datetime.strptime(date_str, "%Y-%m-%d")
        return format_date(dt_obj, format='full', locale=locale_code)
    except ValueError:
        return date_str # Return original if parsing fails

@app.template_filter("format_time")
def format_time_filter(time_str: str, locale_code: str = 'en'):
    try:
        dt_obj = datetime.strptime(time_str, "%H:%M").time()
        return format_time(dt_obj, format='short', locale=locale_code)
    except ValueError:
        return time_str

@app.template_filter("format_currency")
def format_currency_filter(amount: float, currency: str, locale_code: str = 'en'):
    try:
        # Use a specific currency symbol if needed for certain locales, e.g., for AR
        if locale_code == 'ar':
             # Babel might not handle all currency symbols perfectly for AR.
             # This is a workaround to ensure it shows the currency symbol.
            return format_currency(amount, currency, format="#,##0.00\u00a0\u00a4", locale=locale_code)
        return format_currency(amount, currency, locale=locale_code)
    except Exception as e:
        logger.error(f"Error formatting currency {amount} {currency} for locale {locale_code}: {e}")
        return f"{amount} {currency}" # Fallback

# Middleware for language detection
@app.middleware("http")
async def add_i18n_middleware(request: Request, call_next):
    lang_code = request.cookies.get("lang", "en")
    i18n.set_locale(lang_code)
    response = await call_next(request)
    return response

@app.get("/health", response_class=HTMLResponse)
async def health_check():
    return "OK"

# --- Authentication Endpoints ---
@app.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request):
    return templates.TemplateResponse("signup.html", {"request": request, "settings": settings})

@app.post("/signup", response_class=HTMLResponse)
async def register_owner(
    request: Request,
    db: Session = Depends(get_db),
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    business_name: str = Form(...),
    slug: str = Form(...),
    phone: Optional[str] = Form(None)
):
    owner = crud.get_owner_by_email(db, email=email)
    if owner:
        return templates.TemplateResponse(
            "signup.html",
            {"request": request, "error": i18n._("Email already registered"), "settings": settings},
            status_code=status.HTTP_400_BAD_REQUEST
        )
    owner = crud.get_owner_by_slug(db, slug=slug)
    if owner:
        return templates.TemplateResponse(
            "signup.html",
            {"request": request, "error": i18n._("Business URL already taken"), "settings": settings},
            status_code=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        owner_in = schemas.OwnerCreate(name=name, email=email, password=password, business_name=business_name, slug=slug, phone=phone)
        crud.create_owner(db=db, owner=owner_in)
        response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
        response.headers["HX-Redirect"] = "/login" # For htmx
        return response
    except Exception as e:
        logger.error(f"Error during owner registration: {e}")
        return templates.TemplateResponse(
            "signup.html",
            {"request": request, "error": i18n._("An unexpected error occurred during signup."), "settings": settings},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "settings": settings})

@app.post("/login", response_class=HTMLResponse)
async def login_for_access_token(
    request: Request,
    db: Session = Depends(get_db),
    form_data: OAuth2PasswordRequestForm = Depends()
):
    owner = crud.authenticate_owner(db, form_data.username, form_data.password)
    if not owner:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": i18n._("Incorrect email or password"), "settings": settings},
            status_code=status.HTTP_401_UNAUTHORIZED
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": owner.email}, expires_delta=access_token_expires
    )
    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(key="access_token", value=access_token, httponly=True, samesite="Lax")
    response.headers["HX-Redirect"] = "/dashboard" # For htmx
    return response

@app.get("/logout", response_class=RedirectResponse)
async def logout():
    response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(key="access_token")
    return response

# --- Owner Dashboard Endpoints ---
@app.get("/dashboard", response_class=HTMLResponse)
async def owner_dashboard(request: Request, db: Session = Depends(get_db), current_owner: models.Owner = Depends(get_current_owner)):
    bookings = crud.get_owner_bookings(db, owner_id=current_owner.id)
    
    # Filter for upcoming bookings
    now = datetime.utcnow()
    upcoming_bookings = []
    for booking in bookings:
        try:
            booking_datetime_str = f"{booking.booking_date} {booking.booking_time}"
            booking_dt = datetime.strptime(booking_datetime_str, "%Y-%m-%d %H:%M")
            if booking_dt > now:
                upcoming_bookings.append(booking)
        except ValueError:
            logger.error(f"Could not parse booking datetime for booking ID {booking.id}: {booking_datetime_str}")
            # Optionally skip or handle malformed dates

    # Parse services and availability
    services = json.loads(current_owner.services_json) if current_owner.services_json else []
    availability = json.loads(current_owner.availability_json) if current_owner.availability_json else {}

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "owner": current_owner,
            "bookings": upcoming_bookings,
            "services": services,
            "availability": availability,
            "settings": settings
        }
    )

@app.post("/dashboard/profile", response_class=HTMLResponse)
async def update_owner_profile_endpoint(
    request: Request,
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(get_current_owner),
    name: str = Form(...),
    business_name: str = Form(...),
    phone: Optional[str] = Form(None)
):
    try:
        owner_update = schemas.OwnerProfileUpdate(name=name, business_name=business_name, phone=phone)
        updated_owner = crud.update_owner_profile(db, current_owner, owner_update)
        # Refresh the dashboard with updated info
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        logger.error(f"Error updating owner profile for owner {current_owner.id}: {e}")
        # Re-render dashboard with error message
        bookings = crud.get_owner_bookings(db, owner_id=current_owner.id)
        services = json.loads(current_owner.services_json) if current_owner.services_json else []
        availability = json.loads(current_owner.availability_json) if current_owner.availability_json else {}
        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "owner": current_owner,
                "bookings": bookings,
                "services": services,
                "availability": availability,
                "error": i18n._("Failed to update profile. Please try again."),
                "settings": settings
            },
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

# Placeholder for service and availability update endpoints
@app.post("/dashboard/services", response_class=HTMLResponse)
async def update_owner_services(
    request: Request,
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(get_current_owner),
    services_json: str = Form(...) # Expecting a JSON string of services
):
    try:
        # Validate services_json against a list of Service schemas if needed
        # For now, just store it
        current_owner.services_json = services_json
        db.add(current_owner)
        db.commit()
        db.refresh(current_owner)
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        logger.error(f"Error updating services for owner {current_owner.id}: {e}")
        return RedirectResponse(url="/dashboard?error=" + i18n._("Failed to update services."), status_code=status.HTTP_303_SEE_OTHER)

@app.post("/dashboard/availability", response_class=HTMLResponse)
async def update_owner_availability(
    request: Request,
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(get_current_owner),
    availability_json: str = Form(...) # Expecting a JSON string of availability
):
    try:
        # Validate availability_json against a dict of Availability schemas if needed
        # For now, just store it
        current_owner.availability_json = availability_json
        db.add(current_owner)
        db.commit()
        db.refresh(current_owner)
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        logger.error(f"Error updating availability for owner {current_owner.id}: {e}")
        return RedirectResponse(url="/dashboard?error=" + i18n._("Failed to update availability."), status_code=status.HTTP_303_SEE_OTHER)


# --- Public Booking Page Endpoints ---
@app.get("/{owner_slug}", response_class=HTMLResponse)
async def public_booking_page(request: Request, owner_slug: str, db: Session = Depends(get_db)):
    owner = crud.get_owner_by_slug(db, slug=owner_slug)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=i18n._("Owner not found"))

    services = json.loads(owner.services_json) if owner.services_json else []
    availability_raw = json.loads(owner.availability_json) if owner.availability_json else {}
    
    # Process availability for display
    # Example: { "0": [{"start": "09:00", "end": "17:00"}], ... }
    # This logic would be more complex to generate actual slots, but for now, pass raw.

    return templates.TemplateResponse(
        "booking_page.html",
        {
            "request": request,
            "owner": owner,
            "services": services,
            "availability": availability_raw, # Pass raw for client-side processing
            "settings": settings
        }
    )

@app.post("/{owner_slug}/book", response_class=HTMLResponse)
async def submit_booking(
    request: Request,
    owner_slug: str,
    db: Session = Depends(get_db),
    customer_name: str = Form(...),
    customer_email: str = Form(...),
    customer_phone: Optional[str] = Form(None),
    service_name: str = Form(...),
    booking_date: str = Form(...),
    booking_time: str = Form(...)
):
    owner = crud.get_owner_by_slug(db, slug=owner_slug)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=i18n._("Owner not found"))

    try:
        booking_in = schemas.BookingCreate(
            customer_name=customer_name,
            customer_email=customer_email,
            customer_phone=customer_phone,
            service_name=service_name,
            booking_date=booking_date,
            booking_time=booking_time
        )
        booking = crud.create_booking(db=db, booking=booking_in, owner_id=owner.id)

        # Send notifications
        booking_details = f"Service: {booking.service_name}, Date: {booking.booking_date}, Time: {booking.booking_time}, Customer: {booking.customer_name}, Email: {booking.customer_email}, Phone: {booking.customer_phone or 'N/A'}"
        
        # Email to customer
        customer_email_subject = i18n._("Your booking with {business_name} is confirmed").format(business_name=owner.business_name)
        customer_email_html = templates.TemplateResponse(
            "email/customer_confirmation.html",
            {"booking": booking, "owner": owner, "settings": settings, "i18n": i18n._}
        ).body.decode("utf-8")
        notifications.send_email_notification(booking.customer_email, customer_email_subject, customer_email_html)

        # Email to owner
        owner_email_subject = i18n._("New booking for {business_name}").format(business_name=owner.business_name)
        owner_email_html = templates.TemplateResponse(
            "email/owner_notification.html",
            {"booking": booking, "owner": owner, "settings": settings, "i18n": i18n._}
        ).body.decode("utf-8")
        notifications.send_email_notification(owner.email, owner_email_subject, owner_email_html)

        # WhatsApp to owner (if phone available)
        if owner.phone:
            owner_whatsapp_message = i18n._("New booking! {booking_details}").format(booking_details=booking_details)
            notifications.send_whatsapp_notification(owner.phone, owner_whatsapp_message)
        
        # WhatsApp to customer (if phone available)
        if booking.customer_phone:
            customer_whatsapp_message = i18n._("Your booking with {business_name} is confirmed! {booking_details}").format(business_name=owner.business_name, booking_details=booking_details)
            notifications.send_whatsapp_notification(booking.customer_phone, customer_whatsapp_message)

        # Redirect to confirmation page
        response = RedirectResponse(url=f"/{owner_slug}/confirmation", status_code=status.HTTP_303_SEE_OTHER)
        response.headers["HX-Redirect"] = f"/{owner_slug}/confirmation"
        return response

    except Exception as e:
        logger.error(f"Error processing booking for {owner_slug}: {e}")
        # Re-render booking page with error message
        services = json.loads(owner.services_json) if owner.services_json else []
        availability_raw = json.loads(owner.availability_json) if owner.availability_json else {}
        return templates.TemplateResponse(
            "booking_page.html",
            {
                "request": request,
                "owner": owner,
                "services": services,
                "availability": availability_raw,
                "error": i18n._("Failed to submit booking. Please check your details and try again."),
                "settings": settings
            },
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@app.get("/{owner_slug}/confirmation", response_class=HTMLResponse)
async def booking_confirmation_page(request: Request, owner_slug: str, db: Session = Depends(get_db)):
    owner = crud.get_owner_by_slug(db, slug=owner_slug)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=i18n._("Owner not found"))
    return templates.TemplateResponse(
        "booking_confirmation.html",
        {"request": request, "owner": owner, "settings": settings}
    )

# Language toggle endpoint
@app.post("/set-language/{lang_code}", response_class=Response)
async def set_language(lang_code: str, request: Request):
    response = Response(status_code=status.HTTP_200_OK)
    response.set_cookie(key="lang", value=lang_code, httponly=False, samesite="Lax", max_age=31536000) # 1 year
    # If htmx request, trigger a refresh
    if "HX-Request" in request.headers:
        response.headers["HX-Refresh"] = "true"
    return response

# Root redirect to login for now
@app.get("/", response_class=RedirectResponse, include_in_schema=False)
async def root():
    return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
