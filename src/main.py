from fastapi import FastAPI, Depends, HTTPException, status, Request, Form, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, date
import json
import logging
import gettext
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import PlainTextResponse

from . import models, schemas, crud, security, notifications
from .database import SessionLocal, engine, create_tables, get_db
from .config import settings
from .i18n_config import get_jinja_env

logger = logging.getLogger(__name__)

# Create database tables on startup
create_tables()

app = FastAPI()

# Add SessionMiddleware for managing user sessions (e.g., for login, language)
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

# Middleware to set language and make gettext available
class LanguageMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        locale = request.session.get("lang", "en")
        request.state.locale = locale
        request.state.gettext = gettext.translation('messages', settings.LOCALES_DIR, languages=[locale], fallback=True)
        response = await call_next(request)
        return response

app.add_middleware(LanguageMiddleware)

@app.get("/health")
async def health_check():
    return {"status": "ok"}

# Helper to get Jinja2 environment with current locale
def get_template_env(request: Request):
    return get_jinja_env(request.state.locale)

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    _ = request.state.gettext.gettext
    env = get_template_env(request)
    template = env.get_template("signup.html")
    return template.render(request=request, title=_("Welcome to BookSlot"))

@app.post("/token", response_model=schemas.Token)
async def login_for_access_token(request: Request, db: Session = Depends(get_db), form_data: OAuth2PasswordRequestForm = Depends()):
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
    request.session["token"] = access_token # Store token in session
    request.session["owner_id"] = owner.id
    request.session["owner_slug"] = owner.slug
    return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)

@app.post("/signup", response_class=HTMLResponse)
async def owner_signup(
    request: Request,
    db: Session = Depends(get_db),
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    business_name: str = Form(...),
    slug: str = Form(...),
    phone: Optional[str] = Form(None),
):
    _ = request.state.gettext.gettext
    env = get_template_env(request)
    
    db_owner = crud.get_owner_by_email(db, email=email)
    if db_owner:
        template = env.get_template("signup.html")
        return template.render(request=request, error_message=_("Email already registered"), name=name, email=email, business_name=business_name, slug=slug, phone=phone)
    
    db_slug_owner = crud.get_owner_by_slug(db, slug=slug)
    if db_slug_owner:
        template = env.get_template("signup.html")
        return template.render(request=request, error_message=_("Business URL already taken"), name=name, email=email, business_name=business_name, slug=slug, phone=phone)

    owner_create = schemas.OwnerCreate(
        name=name, email=email, password=password, business_name=business_name, slug=slug, phone=phone
    )
    owner = crud.create_owner(db=db, owner=owner_create)
    
    # Auto-login after signup
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": owner.email}, expires_delta=access_token_expires
    )
    request.session["token"] = access_token
    request.session["owner_id"] = owner.id
    request.session["owner_slug"] = owner.slug
    
    return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    _ = request.state.gettext.gettext
    env = get_template_env(request)
    template = env.get_template("login.html")
    return template.render(request=request, title=_("Login to BookSlot"))

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

@app.get("/dashboard", response_class=HTMLResponse)
async def owner_dashboard(request: Request, db: Session = Depends(get_db)):
    _ = request.state.gettext.gettext
    env = get_template_env(request)
    
    token = request.session.get("token")
    if not token:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    
    try:
        current_owner = await security.get_current_owner(db, token)
    except HTTPException:
        request.session.clear()
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    
    bookings_data = crud.get_owner_bookings(db, current_owner.id)
    
    # Filter for upcoming bookings
    today = date.today()
    upcoming_bookings = [
        b for b in bookings_data 
        if b.booking_date.date() >= today
    ]
    upcoming_bookings.sort(key=lambda x: (x.booking_date, x.booking_time))

    # Parse services and availability
    services = json.loads(current_owner.services_json) if current_owner.services_json else []
    availability = json.loads(current_owner.availability_json) if current_owner.availability_json else {}

    template = env.get_template("dashboard.html")
    return template.render(
        request=request, 
        owner=current_owner, 
        upcoming_bookings=upcoming_bookings,
        services=services,
        availability=availability,
        title=_("Dashboard")
    )

@app.post("/dashboard/profile", response_class=HTMLResponse)
async def update_owner_profile(
    request: Request,
    db: Session = Depends(get_db),
    name: str = Form(...),
    business_name: str = Form(...),
    phone: Optional[str] = Form(None),
    services_json: str = Form("[]"), # Expect JSON string from form
    availability_json: str = Form("{}"), # Expect JSON string from form
):
    _ = request.state.gettext.gettext
    env = get_template_env(request)

    token = request.session.get("token")
    if not token:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    
    try:
        current_owner = await security.get_current_owner(db, token)
    except HTTPException:
        request.session.clear()
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    
    try:
        # Validate incoming JSON strings for services and availability
        parsed_services = json.loads(services_json)
        parsed_availability = json.loads(availability_json)

        # Use Pydantic for validation
        schemas.OwnerProfileUpdate(
            name=name, business_name=business_name, email=current_owner.email, slug=current_owner.slug,
            phone=phone, services=parsed_services, availability=parsed_availability
        )
        
        # Update owner details
        current_owner.name = name
        current_owner.business_name = business_name
        current_owner.phone = phone
        current_owner.services_json = services_json
        current_owner.availability_json = availability_json
        
        db.add(current_owner)
        db.commit()
        db.refresh(current_owner)

        return RedirectResponse(url="/dashboard?success=profile_updated", status_code=status.HTTP_302_FOUND)
    except json.JSONDecodeError:
        error_message = _("Invalid JSON format for services or availability.")
        logger.error(f"JSON Decode Error: {error_message}")
    except Exception as e:
        error_message = _(f"Error updating profile: {e}")
        logger.error(f"Profile Update Error: {e}")

    # If error, re-render dashboard with error message
    bookings_data = crud.get_owner_bookings(db, current_owner.id)
    today = date.today()
    upcoming_bookings = [b for b in bookings_data if b.booking_date.date() >= today]
    upcoming_bookings.sort(key=lambda x: (x.booking_date, x.booking_time))
    
    template = env.get_template("dashboard.html")
    return template.render(
        request=request, 
        owner=current_owner, 
        upcoming_bookings=upcoming_bookings,
        services=json.loads(current_owner.services_json),
        availability=json.loads(current_owner.availability_json),
        error_message=error_message,
        title=_("Dashboard")
    )


@app.get("/bookslot/{slug}", response_class=HTMLResponse)
async def booking_page(request: Request, slug: str, db: Session = Depends(get_db)):
    _ = request.state.gettext.gettext
    env = get_template_env(request)
    owner = crud.get_owner_by_slug(db, slug=slug)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Business not found"))
    
    services = json.loads(owner.services_json) if owner.services_json else []
    availability = json.loads(owner.availability_json) if owner.availability_json else {}

    template = env.get_template("booking_page.html")
    return template.render(request=request, owner=owner, services=services, availability=availability, title=owner.business_name)

@app.post("/bookslot/{slug}/submit", response_class=HTMLResponse)
async def submit_booking(
    request: Request,
    slug: str,
    db: Session = Depends(get_db),
    customer_name: str = Form(...),
    customer_email: str = Form(...),
    customer_phone: Optional[str] = Form(None),
    service_name: str = Form(...),
    booking_date: str = Form(...),
    booking_time: str = Form(...),
):
    _ = request.state.gettext.gettext
    env = get_template_env(request)
    owner = crud.get_owner_by_slug(db, slug=slug)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Business not found"))

    try:
        # Basic validation for date and time
        booking_datetime = datetime.strptime(f"{booking_date} {booking_time}", "%Y-%m-%d %H:%M")
        if booking_datetime < datetime.now():
            raise ValueError(_("Cannot book in the past."))

        # Further availability checks (simplified, needs more robust logic for actual slot blocking)
        # For MVP, we assume the frontend provides valid slots based on availability_json
        
        booking_data = schemas.BookingCreate(
            customer_name=customer_name,
            customer_email=customer_email,
            customer_phone=customer_phone,
            service_name=service_name,
            booking_date=booking_date,
            booking_time=booking_time,
        )
        crud.create_booking(db=db, booking=booking_data, owner_id=owner.id)

        # Send notifications
        notifications.send_booking_confirmation_email(
            owner_email=owner.email, 
            customer_email=customer_email, 
            booking_details=booking_data.dict(),
            owner_name=owner.name,
            customer_name=customer_name
        )
        if owner.phone or customer_phone:
            notifications.send_booking_whatsapp_notification(
                owner_phone=owner.phone, 
                customer_phone=customer_phone, 
                booking_details=booking_data.dict(),
                owner_name=owner.name,
                customer_name=customer_name
            )

        template = env.get_template("booking_confirmation.html")
        return template.render(request=request, owner=owner, booking=booking_data, title=_("Booking Confirmed!"))

    except ValueError as e:
        error_message = str(e)
        logger.error(f"Booking submission error: {e}")
    except Exception as e:
        error_message = _(f"An unexpected error occurred: {e}")
        logger.error(f"Unexpected booking submission error: {e}")

    services = json.loads(owner.services_json) if owner.services_json else []
    availability = json.loads(owner.availability_json) if owner.availability_json else {}
    template = env.get_template("booking_page.html")
    return template.render(
        request=request, 
        owner=owner, 
        services=services, 
        availability=availability, 
        error_message=error_message,
        customer_name=customer_name, # Repopulate form fields
        customer_email=customer_email,
        customer_phone=customer_phone,
        selected_service=service_name,
        selected_date=booking_date,
        selected_time=booking_time,
        title=owner.business_name
    )

@app.get("/set_language/{lang}")
async def set_language(request: Request, lang: str):
    request.session["lang"] = lang
    referer = request.headers.get("referer", "/")
    return RedirectResponse(url=referer, status_code=status.HTTP_302_FOUND)
