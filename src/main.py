from fastapi import FastAPI, Depends, HTTPException, status, Request, Form, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
import json
import datetime
import os
import logging
from . import models, schemas, crud, security, notifications
from .database import SessionLocal, engine, Base, get_db
from .config import settings
from .i18n_config import get_jinja_env
from starlette.middleware.sessions import SessionMiddleware
from gettext import gettext as _ # Default gettext for direct Python use

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create tables on startup (for development and testing, migrations for production)
Base.metadata.create_all(bind=engine)

app = FastAPI()

# Mount static files
# Ensure the 'static' directory exists at the project root
STATIC_DIR = os.path.join(settings.PROJECT_ROOT, 'static')
if not os.path.exists(STATIC_DIR):
    os.makedirs(STATIC_DIR)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Add SessionMiddleware for language and session handling
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

# Dependency for Jinja2 environment with i18n
def get_jinja_environment(request: Request):
    locale = request.session.get('locale', 'en')
    return get_jinja_env(locale)

# Dependency to get a database session for testing
def override_get_db():
    try:
        if settings.TESTING:
            # Use in-memory SQLite for testing
            TEST_DATABASE_URL = "sqlite:///:memory:"
            test_engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
            TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
            Base.metadata.create_all(bind=test_engine) # Create tables for in-memory DB
            db = TestingSessionLocal()
        else:
            db = SessionLocal()
        yield db
    finally:
        if 'db' in locals() and db:
            db.close()

# Override the get_db dependency for testing
if settings.TESTING:
    app.dependency_overrides[get_db] = override_get_db

@app.get("/health", response_class=HTMLResponse)
async def health_check():
    return "<h1>OK</h1>"

@app.get("/", response_class=RedirectResponse)
async def root():
    return RedirectResponse(url="/dashboard")

@app.get("/signup", response_class=HTMLResponse)
async def signup_form(request: Request, jinja_env: Any = Depends(get_jinja_environment)):
    template = jinja_env.get_template("signup.html")
    return template.render(request=request, error_message=None)

@app.post("/signup", response_class=HTMLResponse)
async def signup_owner(request: Request, db: Session = Depends(get_db),
                       name: str = Form(...), email: str = Form(...), password: str = Form(...),
                       business_name: str = Form(...), slug: str = Form(...), phone: Optional[str] = Form(None),
                       jinja_env: Any = Depends(get_jinja_environment)):
    template = jinja_env.get_template("signup.html")
    if crud.get_owner_by_email(db, email=email):
        return template.render(request=request, error_message=_("Email already registered."))
    if crud.get_owner_by_slug(db, slug=slug):
        return template.render(request=request, error_message=_("Business URL slug already taken."))

    try:
        owner = schemas.OwnerCreate(name=name, email=email, password=password,
                                    business_name=business_name, slug=slug, phone=phone)
        db_owner = crud.create_owner(db=db, owner=owner)
        if not db_owner:
            raise HTTPException(status_code=500, detail=_("Failed to create owner."))
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        logger.error(f"Signup error: {e}")
        return template.render(request=request, error_message=_("An unexpected error occurred during signup."))

@app.get("/login", response_class=HTMLResponse)
async def login_form(request: Request, jinja_env: Any = Depends(get_jinja_environment)):
    template = jinja_env.get_template("login.html")
    return template.render(request=request, error_message=None)

@app.post("/login", response_class=RedirectResponse)
async def login_for_access_token(request: Request, response: Response, db: Session = Depends(get_db),
                                 form_data: OAuth2PasswordRequestForm = Depends(),
                                 jinja_env: Any = Depends(get_jinja_environment)):
    template = jinja_env.get_template("login.html")
    owner = crud.authenticate_owner(db, email=form_data.username, password=form_data.password)
    if not owner:
        return template.render(request=request, error_message=_("Incorrect email or password."))

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": owner.email}, expires_delta=access_token_expires
    )
    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(key="access_token", value=f"Bearer {access_token}", httponly=True, samesite="lax")
    return response

@app.get("/logout", response_class=RedirectResponse)
async def logout(response: Response):
    response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(key="access_token")
    return response

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db),
                    current_owner: models.Owner = Depends(security.get_current_owner),
                    jinja_env: Any = Depends(get_jinja_environment)):
    bookings = crud.get_owner_bookings(db, owner_id=current_owner.id)
    # Filter for upcoming bookings
    today = datetime.date.today()
    upcoming_bookings = [
        b for b in bookings
        if b.booking_date >= today
    ]
    upcoming_bookings.sort(key=lambda x: (x.booking_date, x.booking_time)) # Sort by date then time

    # Parse services and availability from JSON
    services = json.loads(current_owner.services_json) if current_owner.services_json else []
    availability = json.loads(current_owner.availability_json) if current_owner.availability_json else {}

    template = jinja_env.get_template("dashboard.html")
    return template.render(
        request=request,
        owner=current_owner,
        bookings=upcoming_bookings,
        services=services,
        availability=availability,
        error_message=None,
        success_message=None
    )

@app.post("/profile", response_class=HTMLResponse)
async def update_profile(request: Request, db: Session = Depends(get_db),
                         current_owner: models.Owner = Depends(security.get_current_owner),
                         name: str = Form(...), business_name: str = Form(...),
                         phone: Optional[str] = Form(None),
                         services_json: str = Form("[]"), availability_json: str = Form("{}"),
                         jinja_env: Any = Depends(get_jinja_environment)):
    template = jinja_env.get_template("dashboard.html") # Render dashboard on success/failure

    try:
        # Validate services_json and availability_json
        services_data = json.loads(services_json)
        availability_data = json.loads(availability_json)

        # Basic validation for services (list of dicts with 'name' and 'duration')
        if not isinstance(services_data, list):
            raise ValueError(_("Services must be a list."))
        for service in services_data:
            if not isinstance(service, dict) or 'name' not in service or 'duration' not in service:
                raise ValueError(_("Each service must have 'name' and 'duration'."))

        # Basic validation for availability (dict of days with start/end times)
        if not isinstance(availability_data, dict):
            raise ValueError(_("Availability must be a dictionary."))
        for day, slots in availability_data.items():
            if not isinstance(slots, list):
                raise ValueError(_(f"Availability for {day} must be a list of slots."))
            for slot in slots:
                if not isinstance(slot, dict) or 'start' not in slot or 'end' not in slot:
                    raise ValueError(_(f"Each slot for {day} must have 'start' and 'end' times."))

        owner_update = schemas.OwnerProfileUpdate(
            name=name,
            business_name=business_name,
            phone=phone,
            services=services_data, # These are validated, but crud expects json string
            availability=availability_data # These are validated, but crud expects json string
        )

        # Update owner details
        updated_owner = crud.update_owner_profile(db, current_owner, owner_update)
        updated_owner.services_json = services_json
        updated_owner.availability_json = availability_json
        db.add(updated_owner)
        db.commit()
        db.refresh(updated_owner)

        bookings = crud.get_owner_bookings(db, owner_id=updated_owner.id)
        # Filter for upcoming bookings
        today = datetime.date.today()
        upcoming_bookings = [
            b for b in bookings
            if b.booking_date >= today
        ]
        upcoming_bookings.sort(key=lambda x: (x.booking_date, x.booking_time)) # Sort by date then time

        return template.render(
            request=request,
            owner=updated_owner,
            bookings=upcoming_bookings,
            services=services_data,
            availability=availability_data,
            success_message=_("Profile updated successfully!"),
            error_message=None
        )
    except json.JSONDecodeError:
        error_msg = _("Invalid JSON format for services or availability.")
    except ValueError as ve:
        error_msg = str(ve)
    except Exception as e:
        logger.error(f"Profile update error: {e}")
        error_msg = _("An unexpected error occurred during profile update.")

    # On error, re-render dashboard with current_owner's (pre-update) data and error message
    current_services = json.loads(current_owner.services_json) if current_owner.services_json else []
    current_availability = json.loads(current_owner.availability_json) if current_owner.availability_json else {}
    bookings = crud.get_owner_bookings(db, owner_id=current_owner.id)
    today = datetime.date.today()
    upcoming_bookings = [b for b in bookings if b.booking_date >= today]
    upcoming_bookings.sort(key=lambda x: (x.booking_date, x.booking_time))

    return template.render(
        request=request,
        owner=current_owner,
        bookings=upcoming_bookings,
        services=current_services,
        availability=current_availability,
        error_message=error_msg,
        success_message=None
    )

@app.get("/{owner_slug}", response_class=HTMLResponse)
async def public_booking_page(request: Request, owner_slug: str, db: Session = Depends(get_db),
                              jinja_env: Any = Depends(get_jinja_environment)):
    owner = crud.get_owner_by_slug(db, slug=owner_slug)
    if not owner:
        raise HTTPException(status_code=404, detail=_("Booking page not found."))

    services = json.loads(owner.services_json) if owner.services_json else []
    availability = json.loads(owner.availability_json) if owner.availability_json else {}

    template = jinja_env.get_template("booking_page.html")
    return template.render(request=request, owner=owner, services=services,
                            availability=availability, error_message=None)

@app.post("/{owner_slug}/book", response_class=HTMLResponse)
async def submit_booking(request: Request, owner_slug: str, db: Session = Depends(get_db),
                         customer_name: str = Form(...), customer_email: EmailStr = Form(...),
                         customer_phone: Optional[str] = Form(None),
                         service_name: str = Form(...), booking_date_str: str = Form(...),
                         booking_time: str = Form(...),
                         jinja_env: Any = Depends(get_jinja_environment)):

    owner = crud.get_owner_by_slug(db, slug=owner_slug)
    if not owner:
        raise HTTPException(status_code=404, detail=_("Booking page not found."))

    template = jinja_env.get_template("booking_page.html") # Render booking page on error

    try:
        booking_date = datetime.datetime.strptime(booking_date_str, "%Y-%m-%d").date()
    except ValueError:
        return template.render(request=request, owner=owner, services=json.loads(owner.services_json),
                                availability=json.loads(owner.availability_json),
                                error_message=_("Invalid date format."))

    # Basic availability check (more complex logic needed for real-time slot checking)
    availability = json.loads(owner.availability_json)
    day_of_week = booking_date.strftime('%A').lower() # e.g., 'monday'
    if day_of_week not in availability:
        return template.render(request=request, owner=owner, services=json.loads(owner.services_json),
                                availability=json.loads(owner.availability_json),
                                error_message=_("Owner is not available on this day."))

    # Find the selected service to get its duration
    services_list = json.loads(owner.services_json)
    selected_service = next((s for s in services_list if s.get('name') == service_name), None)
    if not selected_service:
        return template.render(request=request, owner=owner, services=json.loads(owner.services_json),
                                availability=json.loads(owner.availability_json),
                                error_message=_("Selected service is not valid."))
    service_duration = selected_service.get('duration', 30) # Default to 30 mins if not specified

    # More granular slot availability check would involve checking against existing bookings
    # For MVP, we assume any available slot in availability_json is bookable if not taken.
    # This example does NOT implement a sophisticated slot conflict check.
    # It just checks if the _day_ is generally available.
    # A full implementation would parse start/end times from availability and check if the requested
    # booking_time + service_duration fits into an open slot without overlapping existing bookings.

    # For simplicity, let's just check if the time falls within any of the defined slots for the day
    is_time_available = False
    for slot in availability.get(day_of_week, []):
        slot_start = datetime.datetime.strptime(slot['start'], "%H:%M").time()
        slot_end = datetime.datetime.strptime(slot['end'], "%H:%M").time()
        requested_time = datetime.datetime.strptime(booking_time, "%H:%M").time()

        # Check if requested time is within any available slot
        # This is a basic check. A real system would check for duration and conflicts.
        if slot_start <= requested_time < slot_end:
            is_time_available = True
            break
    
    if not is_time_available:
        return template.render(request=request, owner=owner, services=json.loads(owner.services_json),
                                availability=json.loads(owner.availability_json),
                                error_message=_("The selected time is not available or conflicts with existing bookings."))


    try:
        booking_data = schemas.BookingCreate(
            customer_name=customer_name,
            customer_email=customer_email,
            customer_phone=customer_phone,
            service_name=service_name,
            booking_date=booking_date,
            booking_time=booking_time
        )
        db_booking = crud.create_booking(db=db, booking=booking_data, owner_id=owner.id)

        # Send email notifications
        customer_subject = _("Your booking with {} is confirmed!").format(owner.business_name)
        owner_subject = _("New booking received for {}!").format(owner.business_name)

        # Render email content using Jinja2
        email_jinja_env = get_jinja_env(request.session.get('locale', 'en'))
        customer_email_template = email_jinja_env.get_template("email/customer_confirmation.html")
        owner_email_template = email_jinja_env.get_template("email/owner_notification.html")

        booking_details_for_email = {
            "customer_name": customer_name,
            "customer_email": customer_email,
            "customer_phone": customer_phone,
            "service_name": service_name,
            "booking_date": booking_date.strftime("%Y-%m-%d"),
            "booking_time": booking_time,
            "owner_business_name": owner.business_name,
            "owner_name": owner.name,
            "owner_email": owner.email,
            "owner_phone": owner.phone,
            "public_booking_link": request.url_for("public_booking_page", owner_slug=owner.slug)
        }

        customer_html_content = customer_email_template.render(booking=booking_details_for_email)
        owner_html_content = owner_email_template.render(booking=booking_details_for_email)

        notifications.send_email_notification(customer_email, customer_subject, customer_html_content)
        notifications.send_email_notification(owner.email, owner_subject, owner_html_content)

        # Send WhatsApp notification to owner
        if owner.phone:
            whatsapp_message = _("New booking for {service_name} on {date} at {time} by {customer_name}. Customer phone: {customer_phone}").format(
                service_name=service_name,
                date=booking_date.strftime("%Y-%m-%d"),
                time=booking_time,
                customer_name=customer_name,
                customer_phone=customer_phone or _("N/A")
            )
            notifications.send_whatsapp_notification(owner.phone, whatsapp_message)

        return RedirectResponse(url=f"/{owner_slug}/confirmed", status_code=status.HTTP_303_SEE_OTHER)

    except Exception as e:
        logger.error(f"Booking submission error: {e}")
        return template.render(request=request, owner=owner, services=json.loads(owner.services_json),
                                availability=json.loads(owner.availability_json),
                                error_message=_("An unexpected error occurred during booking. Please try again."))

@app.get("/{owner_slug}/confirmed", response_class=HTMLResponse)
async def booking_confirmation_page(request: Request, owner_slug: str, db: Session = Depends(get_db),
                                    jinja_env: Any = Depends(get_jinja_environment)):
    owner = crud.get_owner_by_slug(db, slug=owner_slug)
    if not owner:
        raise HTTPException(status_code=404, detail=_("Booking page not found."))
    template = jinja_env.get_template("booking_confirmation.html")
    return template.render(request=request, owner=owner)

@app.get("/set_language/{lang}", response_class=RedirectResponse)
async def set_language(request: Request, lang: str, redirect_to: str = "/", response: Response = Response()):
    if lang in ['en', 'ar', 'fr']:
        request.session['locale'] = lang
    else:
        request.session['locale'] = 'en' # Default to English if invalid language
    
    # Redirect back to the page the user was on
    return RedirectResponse(url=redirect_to, status_code=status.HTTP_303_SEE_OTHER)
