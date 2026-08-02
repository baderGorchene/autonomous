from fastapi import FastAPI, Depends, HTTPException, status, Request, Form, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from typing import List, Optional
import json
import datetime
import logging

from . import crud, models, schemas, security, dependencies, notifications
from .database import engine, create_tables, get_db, drop_tables
from .config import settings
from .i18n_config import get_templates_env
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

# Initialize logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create database tables on startup, only if not in testing mode
# This ensures tables are created for actual app run, but not during test setup
if not settings.TESTING:
    create_tables()

app = FastAPI()

# Middleware for language detection and setting
@app.middleware("http")
async def add_language_middleware(request: Request, call_next):
    lang = request.query_params.get("lang", "en")
    if lang not in ["en", "ar", "fr"]:
        lang = "en" # Default to English if invalid
    request.state.lang = lang
    response = await call_next(request)
    return response

# Helper for translating API error messages or logs
def _(text: str, request: Request = None):
    if request and hasattr(request.state, 'lang'):
        templates_instance = get_templates_env(request)
        if hasattr(templates_instance.env, 'gettext'):
            return templates_instance.env.gettext(text)
    return text # Fallback if no request or gettext not set

# --- API Endpoints ---

@app.post("/token", response_model=schemas.Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    owner = crud.authenticate_owner(db, form_data.username, form_data.password)
    if not owner:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = datetime.timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": owner.email}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/api/owner/me", response_model=schemas.Owner)
async def read_owner_me(current_owner: models.Owner = Depends(dependencies.get_current_owner)):
    return current_owner

@app.post("/api/owner/signup", response_model=schemas.Owner)
async def create_owner_api(owner: schemas.OwnerCreate, db: Session = Depends(get_db)):
    db_owner = crud.get_owner_by_email(db, email=owner.email)
    if db_owner:
        raise HTTPException(status_code=400, detail="Email already registered")
    db_owner_slug = crud.get_owner_by_slug(db, slug=owner.slug)
    if db_owner_slug:
        raise HTTPException(status_code=400, detail="Business URL already taken")
    return crud.create_owner(db=db, owner=owner)

@app.put("/api/owner/profile", response_model=schemas.Owner)
async def update_owner_profile_api(
    owner_update: schemas.OwnerProfileUpdate,
    current_owner: models.Owner = Depends(dependencies.get_current_owner),
    db: Session = Depends(get_db)
):
    try:
        # Update basic profile fields
        current_owner = crud.update_owner_profile(db, current_owner, owner_update)

        # Update services if provided
        if owner_update.services is not None:
            current_owner.services_json = json.dumps([s.dict() for s in owner_update.services])

        # Update availability if provided
        if owner_update.availability is not None:
            current_owner.availability_json = json.dumps([a.dict() for a in owner_update.availability])
        
        db.add(current_owner)
        db.commit()
        db.refresh(current_owner)
        return current_owner
    except Exception as e:
        logger.error(f"Error updating owner profile: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to update profile: {e}")

@app.post("/api/booking/{owner_slug}", response_model=schemas.BookingConfirmation)
async def create_booking_api(
    owner_slug: str,
    booking: schemas.BookingCreate,
    request: Request,
    db: Session = Depends(get_db)
):
    owner = crud.get_owner_by_slug(db, slug=owner_slug)
    if not owner:
        raise HTTPException(status_code=404, detail=_("Owner not found.", request))

    # Basic availability check (can be more sophisticated)
    owner_availability = json.loads(owner.availability_json) if owner.availability_json else []
    booking_weekday = booking.booking_date.weekday() # Monday is 0, Sunday is 6
    booking_time_obj = datetime.datetime.strptime(booking.booking_time, "%H:%M").time()

    is_available = False
    for slot in owner_availability:
        if slot['day_of_week'] == booking_weekday:
            slot_start = datetime.datetime.strptime(slot['start_time'], "%H:%M").time()
            slot_end = datetime.datetime.strptime(slot['end_time'], "%H:%M").time()
            if slot_start <= booking_time_obj < slot_end:
                is_available = True
                break
    
    if not is_available:
        raise HTTPException(status_code=400, detail=_("Selected time slot is not available.", request))

    # Check for existing bookings to prevent double-booking (simple check)
    existing_bookings = db.query(models.Booking).filter(
        models.Booking.owner_id == owner.id,
        models.Booking.booking_date == booking.booking_date,
        models.Booking.booking_time == booking.booking_time
    ).first()

    if existing_bookings:
        raise HTTPException(status_code=409, detail=_("This slot is already booked. Please choose another time.", request))

    try:
        db_booking = crud.create_booking(db=db, booking=booking, owner_id=owner.id)

        # Send notifications
        # Owner notification
        owner_subject = _("New Booking for {service_name}!", request).format(service_name=booking.service_name)
        owner_html = _("""
            <p>Dear {owner_name},</p>
            <p>You have a new booking!</p>
            <ul>
                <li>Service: {service_name}</li>
                <li>Date: {booking_date}</li>
                <li>Time: {booking_time}</li>
                <li>Customer Name: {customer_name}</li>
                <li>Customer Email: {customer_email}</li>
                <li>Customer Phone: {customer_phone}</li>
            </ul>
            <p>BookSlot App</p>
        """, request).format(
            owner_name=owner.name,
            service_name=booking.service_name,
            booking_date=booking.booking_date.strftime('%Y-%m-%d'),
            booking_time=booking.booking_time,
            customer_name=booking.customer_name,
            customer_email=booking.customer_email,
            customer_phone=booking.customer_phone or _("N/A", request)
        )
        notifications.send_email_notification(owner.email, owner_subject, owner_html)
        if owner.phone:
            owner_whatsapp_msg = _("New booking for {service_name} on {booking_date} at {booking_time} with {customer_name}.", request).format(
                service_name=booking.service_name,
                booking_date=booking.booking_date.strftime('%Y-%m-%d'),
                booking_time=booking.booking_time,
                customer_name=booking.customer_name
            )
            notifications.send_whatsapp_notification(owner.phone, owner_whatsapp_msg)

        # Customer confirmation
        customer_subject = _("Your Booking for {service_name} is Confirmed!", request).format(service_name=booking.service_name)
        customer_html = _("""
            <p>Dear {customer_name},</p>
            <p>Your booking with {business_name} for {service_name} on {booking_date} at {booking_time} has been confirmed.</p>
            <p>We look forward to seeing you!</p>
            <p>BookSlot App</p>
        """, request).format(
            customer_name=booking.customer_name,
            business_name=owner.business_name,
            service_name=booking.service_name,
            booking_date=booking.booking_date.strftime('%Y-%m-%d'),
            booking_time=booking.booking_time
        )
        notifications.send_email_notification(booking.customer_email, customer_subject, customer_html)
        if booking.customer_phone:
            customer_whatsapp_msg = _("Your booking with {business_name} for {service_name} on {booking_date} at {booking_time} is confirmed.", request).format(
                business_name=owner.business_name,
                service_name=booking.service_name,
                booking_date=booking.booking_date.strftime('%Y-%m-%d'),
                booking_time=booking.booking_time
            )
            notifications.send_whatsapp_notification(booking.customer_phone, customer_whatsapp_msg)

        return schemas.BookingConfirmation(
            message=_("Booking confirmed successfully!", request),
            booking_id=db_booking.id
        )
    except Exception as e:
        logger.error(f"Error during booking creation or notification: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=_("Failed to create booking.", request))

# --- HTML Page Endpoints ---

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request, templates_env: Jinja2Templates = Depends(get_templates_env)):
    return templates_env.TemplateResponse("index.html", {"request": request, "_": templates_env.env.gettext})

@app.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request, templates_env: Jinja2Templates = Depends(get_templates_env)):
    return templates_env.TemplateResponse("signup.html", {"request": request, "_": templates_env.env.gettext})

@app.post("/signup", response_class=RedirectResponse)
async def post_signup(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    business_name: str = Form(...),
    slug: str = Form(...),
    phone: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    try:
        owner_create = schemas.OwnerCreate(
            name=name, email=email, password=password,
            business_name=business_name, slug=slug, phone=phone
        )
        crud.create_owner(db, owner_create)
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    except HTTPException as e:
        templates_env = get_templates_env(request)
        return templates_env.TemplateResponse(
            "signup.html",
            {"request": request, "error": e.detail, "name": name, "email": email, "business_name": business_name, "slug": slug, "phone": phone, "_": templates_env.env.gettext},
            status_code=e.status_code
        )
    except Exception as e:
        templates_env = get_templates_env(request)
        return templates_env.TemplateResponse(
            "signup.html",
            {"request": request, "error": _("An unexpected error occurred during signup.", request), "_": templates_env.env.gettext},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, templates_env: Jinja2Templates = Depends(get_templates_env)):
    return templates_env.TemplateResponse("login.html", {"request": request, "_": templates_env.env.gettext})

@app.post("/login", response_class=RedirectResponse)
async def post_login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    owner = crud.authenticate_owner(db, email, password)
    if not owner:
        templates_env = get_templates_env(request)
        return templates_env.TemplateResponse(
            "login.html",
            {"request": request, "error": _("Incorrect email or password.", request), "email": email, "_": templates_env.env.gettext},
            status_code=status.HTTP_401_UNAUTHORIZED
        )
    access_token_expires = datetime.timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": owner.email}, expires_delta=access_token_expires
    )
    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(key="access_token", value=f"Bearer {access_token}", httponly=True, samesite="lax", secure=True) # Secure in prod
    return response

@app.get("/logout", response_class=RedirectResponse)
async def logout(response: Response):
    response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(key="access_token")
    return response

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(
    request: Request,
    current_owner: models.Owner = Depends(dependencies.get_current_owner),
    db: Session = Depends(get_db),
    templates_env: Jinja2Templates = Depends(get_templates_env)
):
    bookings = crud.get_owner_bookings(db, current_owner.id)
    # Parse services and availability from JSON strings
    services = json.loads(current_owner.services_json) if current_owner.services_json else []
    availability = json.loads(current_owner.availability_json) if current_owner.availability_json else []

    return templates_env.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "owner": current_owner,
            "bookings": bookings,
            "services": services,
            "availability": availability,
            "_": templates_env.env.gettext
        }
    )

@app.post("/dashboard/profile", response_class=RedirectResponse)
async def update_profile_page(
    request: Request,
    name: str = Form(...),
    business_name: str = Form(...),
    phone: Optional[str] = Form(None),
    services_json: str = Form("[]"),
    availability_json: str = Form("{}"),
    current_owner: models.Owner = Depends(dependencies.get_current_owner),
    db: Session = Depends(get_db)
):
    try:
        # Validate and parse services and availability
        parsed_services = json.loads(services_json)
        parsed_availability = json.loads(availability_json)

        # Convert to Pydantic models for validation
        services_pydantic = [schemas.ServiceCreate(**s) for s in parsed_services]
        availability_pydantic = [schemas.AvailabilitySlot(**a) for a in parsed_availability]

        owner_update = schemas.OwnerProfileUpdate(
            name=name,
            business_name=business_name,
            phone=phone,
            services=services_pydantic,
            availability=availability_pydantic
        )
        await update_owner_profile_api(owner_update, current_owner, db)
        return RedirectResponse(url="/dashboard?success=true", status_code=status.HTTP_303_SEE_OTHER)
    except json.JSONDecodeError:
        templates_env = get_templates_env(request)
        return templates_env.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "owner": current_owner,
                "bookings": crud.get_owner_bookings(db, current_owner.id),
                "error": _("Invalid JSON format for services or availability.", request),
                "_": templates_env.env.gettext
            },
            status_code=status.HTTP_400_BAD_REQUEST
        )
    except Exception as e:
        logger.error(f"Error updating profile from dashboard: {e}")
        templates_env = get_templates_env(request)
        return templates_env.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "owner": current_owner,
                "bookings": crud.get_owner_bookings(db, current_owner.id),
                "error": _(f"Failed to update profile: {e}", request),
                "_": templates_env.env.gettext
            },
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@app.get("/{owner_slug}", response_class=HTMLResponse)
async def public_booking_page(
    owner_slug: str,
    request: Request,
    db: Session = Depends(get_db),
    templates_env: Jinja2Templates = Depends(get_templates_env)
):
    owner = crud.get_owner_by_slug(db, slug=owner_slug)
    if not owner:
        raise HTTPException(status_code=404, detail=_("Owner not found.", request))

    services = json.loads(owner.services_json) if owner.services_json else []
    availability = json.loads(owner.availability_json) if owner.availability_json else []

    return templates_env.TemplateResponse(
        "booking_page.html",
        {
            "request": request,
            "owner": owner,
            "services": services,
            "availability": availability,
            "owner_slug": owner_slug,
            "_": templates_env.env.gettext
        }
    )

@app.post("/{owner_slug}/book", response_class=HTMLResponse)
async def post_public_booking(
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
    try:
        booking_date_obj = datetime.datetime.strptime(booking_date, "%Y-%m-%d").date()
        booking_create = schemas.BookingCreate(
            customer_name=customer_name,
            customer_email=customer_email,
            customer_phone=customer_phone,
            service_name=service_name,
            booking_date=booking_date_obj,
            booking_time=booking_time
        )
        booking_confirmation = await create_booking_api(owner_slug, booking_create, request, db)
        templates_env = get_templates_env(request)
        return templates_env.TemplateResponse(
            "booking_confirmation.html",
            {
                "request": request,
                "message": booking_confirmation.message,
                "_": templates_env.env.gettext
            }
        )
    except HTTPException as e:
        owner = crud.get_owner_by_slug(db, slug=owner_slug)
        services = json.loads(owner.services_json) if owner.services_json else []
        availability = json.loads(owner.availability_json) if owner.availability_json else []
        templates_env = get_templates_env(request)
        return templates_env.TemplateResponse(
            "booking_page.html",
            {
                "request": request,
                "owner": owner,
                "services": services,
                "availability": availability,
                "owner_slug": owner_slug,
                "error": e.detail,
                "customer_name": customer_name,
                "customer_email": customer_email,
                "customer_phone": customer_phone,
                "selected_service": service_name,
                "selected_date": booking_date,
                "selected_time": booking_time,
                "_": templates_env.env.gettext
            },
            status_code=e.status_code
        )
    except Exception as e:
        logger.error(f"Error during public booking form submission: {e}")
        owner = crud.get_owner_by_slug(db, slug=owner_slug)
        services = json.loads(owner.services_json) if owner.services_json else []
        availability = json.loads(owner.availability_json) if owner.availability_json else []
        templates_env = get_templates_env(request)
        return templates_env.TemplateResponse(
            "booking_page.html",
            {
                "request": request,
                "owner": owner,
                "services": services,
                "availability": availability,
                "owner_slug": owner_slug,
                "error": _("An unexpected error occurred during booking.", request),
                "customer_name": customer_name,
                "customer_email": customer_email,
                "customer_phone": customer_phone,
                "selected_service": service_name,
                "selected_date": booking_date,
                "selected_time": booking_time,
                "_": templates_env.env.gettext
            },
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

# Health check endpoint
@app.get("/health")
async def health_check():
    return {"status": "ok"}
