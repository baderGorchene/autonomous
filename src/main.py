from fastapi import FastAPI, Depends, HTTPException, status, Request, Response, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta, datetime
from typing import List, Optional
import json
import os
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

from . import crud, models, schemas, security, notifications
from .database import SessionLocal, engine
from .config import settings
from .i18n_config import get_jinja_env # Import the configured Jinja2 environment

# Create database tables
models.Base.metadata.create_all(bind=engine)

app = FastAPI()

# OAuth2PasswordBearer for token authentication
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/token")

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Dependency to get current owner
async def get_current_owner(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            detail="Not authenticated",
            headers={"Location": "/login"}
        )
    payload = security.decode_access_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            detail="Invalid token",
            headers={"Location": "/login"}
        )
    email: str = payload.get("sub")
    if email is None:
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            detail="Invalid token payload",
            headers={"Location": "/login"}
        )
    owner = crud.get_owner_by_email(db, email=email)
    if owner is None:
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            detail="Owner not found",
            headers={"Location": "/login"}
        )
    return owner

# Helper to get locale from request or set default
def get_locale(request: Request):
    locale = request.query_params.get('lang', 'en')
    if locale not in ['en', 'ar', 'fr']:
        locale = 'en'
    return locale

# --- Routes ---

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request, db: Session = Depends(get_db)):
    locale = get_locale(request)
    env = get_jinja_env(locale)
    template = env.get_template("index.html") # Assuming an index.html for the landing page
    return template.render(request=request, locale=locale, current_path=request.url.path)

@app.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request):
    locale = get_locale(request)
    env = get_jinja_env(locale)
    template = env.get_template("signup.html")
    return template.render(request=request, locale=locale, current_path=request.url.path)

@app.post("/signup", response_class=HTMLResponse)
async def register_owner(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    business_name: str = Form(...),
    slug: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    locale = get_locale(request)
    env = get_jinja_env(locale)

    db_owner = crud.get_owner_by_email(db, email=email)
    if db_owner:
        template = env.get_template("signup.html")
        return template.render(request=request, error=env.get_template("signup.html").globals['gettext']('Email already registered'), locale=locale, current_path=request.url.path)
    
    db_owner_slug = crud.get_owner_by_slug(db, slug=slug)
    if db_owner_slug:
        template = env.get_template("signup.html")
        return template.render(request=request, error=env.get_template("signup.html").globals['gettext']('Business URL already taken'), locale=locale, current_path=request.url.path)

    owner = schemas.OwnerCreate(name=name, email=email, business_name=business_name, slug=slug, password=password)
    crud.create_owner(db=db, owner=owner)
    
    # Redirect to login page after successful signup
    response = RedirectResponse(url="/login?message=signup_success", status_code=status.HTTP_303_SEE_OTHER)
    return response

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    locale = get_locale(request)
    env = get_jinja_env(locale)
    template = env.get_template("login.html")
    message = request.query_params.get("message")
    return template.render(request=request, locale=locale, message=message, current_path=request.url.path)

@app.post("/login")
async def login_for_access_token(
    request: Request,
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    locale = get_locale(request)
    env = get_jinja_env(locale)
    _ = env.get_template("login.html").globals['gettext'] # Get gettext from template env

    owner = crud.authenticate_owner(db, form_data.username, form_data.password)
    if not owner:
        template = env.get_template("login.html")
        return template.render(request=request, error=_("Incorrect email or password"), locale=locale, current_path=request.url.path)
    
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": owner.email}, expires_delta=access_token_expires
    )
    
    redirect_response = RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    redirect_response.set_cookie(key="access_token", value=access_token, httponly=True, expires=access_token_expires.total_seconds())
    return redirect_response

@app.get("/logout")
async def logout(response: Response):
    redirect_response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    redirect_response.delete_cookie(key="access_token")
    return redirect_response

@app.get("/dashboard", response_class=HTMLResponse)
async def owner_dashboard(request: Request, owner: models.Owner = Depends(get_current_owner), db: Session = Depends(get_db)):
    locale = get_locale(request)
    env = get_jinja_env(locale)

    # Convert JSON strings to Python objects
    services_data = json.loads(owner.services_json) if owner.services_json else []
    availability_data = json.loads(owner.availability_json) if owner.availability_json else {}

    # Fetch upcoming bookings
    upcoming_bookings = db.query(models.Booking).filter(
        models.Booking.owner_id == owner.id,
        models.Booking.booking_time >= datetime.now()
    ).order_by(models.Booking.booking_time).all()

    template = env.get_template("dashboard.html")
    return template.render(
        request=request,
        owner=owner,
        services=services_data,
        availability=availability_data,
        upcoming_bookings=upcoming_bookings,
        locale=locale,
        current_path=request.url.path
    )

@app.post("/dashboard/profile", response_class=HTMLResponse)
async def update_owner_profile(
    request: Request,
    name: str = Form(...),
    business_name: str = Form(...),
    phone: Optional[str] = Form(None),
    services_json: str = Form('[]'), # Expect JSON string from form
    availability_json: str = Form('{}'), # Expect JSON string from form
    owner: models.Owner = Depends(get_current_owner),
    db: Session = Depends(get_db)
):
    locale = get_locale(request)
    env = get_jinja_env(locale)
    _ = env.get_template("dashboard.html").globals['gettext'] # Get gettext from template env

    try:
        # Validate services and availability JSON
        parsed_services = json.loads(services_json)
        parsed_availability = json.loads(availability_json)
        
        # Optional: More rigorous validation against schemas.ServiceSchema and AvailabilitySchema
        # For now, just ensuring they are valid JSON.
        
        owner_update_data = schemas.OwnerProfileUpdate(
            name=name,
            business_name=business_name,
            phone=phone,
            services=parsed_services, # These are not directly used by crud.update_owner_profile
            availability=parsed_availability # These are not directly used by crud.update_owner_profile
        )

        updated_owner = crud.update_owner_profile(db=db, current_owner=owner, owner_update=owner_update_data)
        updated_owner.services_json = services_json # Manually update JSON fields
        updated_owner.availability_json = availability_json
        db.add(updated_owner)
        db.commit()
        db.refresh(updated_owner)

        # Re-fetch bookings for rendering dashboard
        upcoming_bookings = db.query(models.Booking).filter(
            models.Booking.owner_id == updated_owner.id,
            models.Booking.booking_time >= datetime.now()
        ).order_by(models.Booking.booking_time).all()

        template = env.get_template("dashboard.html")
        return template.render(
            request=request,
            owner=updated_owner,
            services=parsed_services,
            availability=parsed_availability,
            upcoming_bookings=upcoming_bookings,
            locale=locale,
            success_message=_("Profile updated successfully!"),
            current_path=request.url.path
        )
    except json.JSONDecodeError:
        # Re-fetch bookings for rendering dashboard
        upcoming_bookings = db.query(models.Booking).filter(
            models.Booking.owner_id == owner.id,
            models.Booking.booking_time >= datetime.now()
        ).order_by(models.Booking.booking_time).all()
        template = env.get_template("dashboard.html")
        return template.render(
            request=request,
            owner=owner,
            services=json.loads(owner.services_json),
            availability=json.loads(owner.availability_json),
            upcoming_bookings=upcoming_bookings,
            locale=locale,
            error_message=_("Invalid JSON format for services or availability."),
            current_path=request.url.path
        )
    except Exception as e:
        # Re-fetch bookings for rendering dashboard
        upcoming_bookings = db.query(models.Booking).filter(
            models.Booking.owner_id == owner.id,
            models.Booking.booking_time >= datetime.now()
        ).order_by(models.Booking.booking_time).all()
        template = env.get_template("dashboard.html")
        return template.render(
            request=request,
            owner=owner,
            services=json.loads(owner.services_json),
            availability=json.loads(owner.availability_json),
            upcoming_bookings=upcoming_bookings,
            locale=locale,
            error_message=f"{_('An unexpected error occurred')}: {e}",
            current_path=request.url.path
        )


@app.get("/{owner_slug}", response_class=HTMLResponse)
async def public_booking_page(owner_slug: str, request: Request, db: Session = Depends(get_db)):
    locale = get_locale(request)
    env = get_jinja_env(locale)
    
    owner = crud.get_owner_by_slug(db, slug=owner_slug)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking page not found")

    services = json.loads(owner.services_json) if owner.services_json else []
    availability = json.loads(owner.availability_json) if owner.availability_json else {}

    template = env.get_template("booking_page.html")
    return template.render(
        request=request,
        owner=owner,
        services=services,
        availability=availability,
        locale=locale,
        current_path=request.url.path
    )

@app.post("/{owner_slug}/book", response_class=HTMLResponse)
async def submit_booking(
    owner_slug: str,
    request: Request,
    customer_name: str = Form(...),
    customer_email: str = Form(...),
    customer_phone: Optional[str] = Form(None),
    service_name: str = Form(...),
    booking_date: str = Form(...),
    booking_time: str = Form(...),
    db: Session = Depends(get_db)
):
    locale = get_locale(request)
    env = get_jinja_env(locale)
    _ = env.get_template("booking_page.html").globals['gettext'] # Get gettext from template env

    owner = crud.get_owner_by_slug(db, slug=owner_slug)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Booking page not found"))

    # Find the selected service to get its duration
    selected_service = next((s for s in json.loads(owner.services_json) if s['name'] == service_name), None)
    if not selected_service:
        # Render booking page with error
        services = json.loads(owner.services_json) if owner.services_json else []
        availability = json.loads(owner.availability_json) if owner.availability_json else {}
        template = env.get_template("booking_page.html")
        return template.render(
            request=request,
            owner=owner,
            services=services,
            availability=availability,
            error_message=_("Selected service not found."),
            locale=locale,
            current_path=request.url.path
        )

    duration_minutes = selected_service['duration_minutes']
    
    try:
        full_booking_time_str = f"{booking_date} {booking_time}"
        parsed_booking_time = datetime.strptime(full_booking_time_str, "%Y-%m-%d %H:%M")
    except ValueError:
        # Render booking page with error
        services = json.loads(owner.services_json) if owner.services_json else []
        availability = json.loads(owner.availability_json) if owner.availability_json else {}
        template = env.get_template("booking_page.html")
        return template.render(
            request=request,
            owner=owner,
            services=services,
            availability=availability,
            error_message=_("Invalid date or time format."),
            locale=locale,
            current_path=request.url.path
        )

    # Basic availability check (more complex logic might be needed for overlapping bookings)
    # This is a simplified check that the chosen time falls within owner's general availability
    day_of_week = parsed_booking_time.weekday() # Monday is 0, Sunday is 6
    owner_availability = json.loads(owner.availability_json)
    
    is_available = False
    for avail_slot in owner_availability.get(str(day_of_week), []):
        start_avail = datetime.strptime(avail_slot['start_time'], "%H:%M").time()
        end_avail = datetime.strptime(avail_slot['end_time'], "%H:%M").time()
        
        booking_start_time = parsed_booking_time.time()
        booking_end_time = (parsed_booking_time + timedelta(minutes=duration_minutes)).time()

        if start_avail <= booking_start_time and end_avail >= booking_end_time:
            is_available = True
            break
    
    if not is_available:
        services = json.loads(owner.services_json) if owner.services_json else []
        availability = json.loads(owner.availability_json) if owner.availability_json else {}
        template = env.get_template("booking_page.html")
        return template.render(
            request=request,
            owner=owner,
            services=services,
            availability=availability,
            error_message=_("The selected time slot is not available."),
            locale=locale,
            current_path=request.url.path
        )

    # Create booking schema
    booking_data = schemas.BookingCreate(
        customer_name=customer_name,
        customer_email=customer_email,
        customer_phone=customer_phone,
        service_name=service_name,
        booking_time=parsed_booking_time,
        duration_minutes=duration_minutes
    )

    try:
        db_booking = crud.create_booking(db=db, booking=booking_data, owner_id=owner.id)

        # Send notifications
        owner_email_html = notifications.get_owner_booking_email_html(
            booking_data.dict(), owner.name, owner.business_name, customer_email, locale
        )
        notifications.send_email(owner.email, _("New Booking Received!"), owner_email_html)
        
        customer_email_html = notifications.get_customer_confirmation_email_html(
            booking_data.dict(), owner.name, owner.business_name, locale
        )
        notifications.send_email(customer_email, _("Your BookSlot Booking is Confirmed!"), customer_email_html)

        if owner.phone:
            owner_whatsapp_message = notifications.format_booking_details(
                booking_data.dict(), owner.name, owner.business_name, locale
            )
            notifications.send_whatsapp_message(owner.phone, owner_whatsapp_message)
        
        if customer_phone:
            customer_whatsapp_message = notifications.format_booking_details(
                booking_data.dict(), owner.name, owner.business_name, locale
            )
            notifications.send_whatsapp_message(customer_phone, customer_whatsapp_message)

        # Redirect to a confirmation page
        redirect_response = RedirectResponse(url=f"/{owner_slug}/booking-confirmation", status_code=status.HTTP_303_SEE_OTHER)
        # Store booking details in session/cookie if needed for confirmation page, or pass as query params
        return redirect_response

    except Exception as e:
        # Render booking page with error
        services = json.loads(owner.services_json) if owner.services_json else []
        availability = json.loads(owner.availability_json) if owner.availability_json else {}
        template = env.get_template("booking_page.html")
        return template.render(
            request=request,
            owner=owner,
            services=services,
            availability=availability,
            error_message=f"{_('An error occurred during booking')}: {e}",
            locale=locale,
            current_path=request.url.path
        )

@app.get("/{owner_slug}/booking-confirmation", response_class=HTMLResponse)
async def booking_confirmation_page(owner_slug: str, request: Request, db: Session = Depends(get_db)):
    locale = get_locale(request)
    env = get_jinja_env(locale)
    
    owner = crud.get_owner_by_slug(db, slug=owner_slug)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking page not found")

    template = env.get_template("booking_confirmation.html")
    return template.render(
        request=request,
        owner=owner,
        locale=locale,
        current_path=request.url.path
    )

# Static files (CSS, JS)
STATIC_DIR = os.path.join(settings.PROJECT_ROOT, 'static')
if os.path.exists(STATIC_DIR):
    from fastapi.staticfiles import StaticFiles
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
