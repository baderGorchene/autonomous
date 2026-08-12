import logging
from logging.handlers import RotatingFileHandler
from fastapi import FastAPI, Depends, HTTPException, status, Request, Response, BackgroundTasks, APIRouter
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, date, time
from typing import List, Optional, Dict, Any
import pytz
from babel.dates import format_datetime, format_date, format_time
from babel.numbers import format_currency
from pathlib import Path
import os
import gettext
import stripe

from . import models, schemas, crud, security, database, notifications, analytics, availability_utils
from .config import settings

# --- Logging Configuration for Security Events ---
log_dir = "logs"
os.makedirs(log_dir, exist_ok=True)
security_log_file = os.path.join(log_dir, "bookslot_security.log")
app_log_file = os.path.join(log_dir, "bookslot_app.log")
max_bytes = 10 * 1024 * 1024  # 10 MB
backup_count = 5

# Custom filter to inject client_ip and username
class ContextFilter(logging.Filter):
    def filter(self, record):
        record.client_ip = getattr(record, 'client_ip', 'N/A')
        record.username = getattr(record, 'username', 'N/A')
        return True

# Security Logger
security_logger = logging.getLogger("security_events")
security_logger.setLevel(logging.INFO)
security_formatter = logging.Formatter(
    "%(asctime)s - %(levelname)s - %(name)s - [IP: %(client_ip)s] [User: %(username)s] - %(message)s"
)
security_file_handler = RotatingFileHandler(security_log_file, maxBytes=max_bytes, backupCount=backup_count)
security_file_handler.setFormatter(security_formatter)
security_logger.addHandler(security_file_handler)
security_logger.addFilter(ContextFilter())

# Application Logger (for general app events, not strictly security)
app_logger = logging.getLogger("app_events")
app_logger.setLevel(logging.INFO)
app_formatter = logging.Formatter(
    "%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)
app_file_handler = RotatingFileHandler(app_log_file, maxBytes=max_bytes, backupCount=backup_count)
app_file_handler.setFormatter(app_formatter)
app_logger.addHandler(app_file_handler)
app_logger.addHandler(logging.StreamHandler()) # Also log to console for app events

# --- FastAPI App Setup ---
app = FastAPI(
    title="BookSlot App",
    description="Dead-simple booking page for local service businesses.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

router = APIRouter()

# --- Templates and i18n Setup ---
BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

LOCALES_DIR = BASE_DIR / "locales"
LANGUAGES = ["en", "ar", "fr"]

def get_locale_negotiator(request: Request):
    lang = request.cookies.get("lang", "en")
    if lang not in LANGUAGES:
        lang = "en"
    return lang

def get_translator(request: Request):
    lang = get_locale_negotiator(request)
    try:
        t = gettext.translation("messages", localedir=LOCALES_DIR, languages=[lang])
        return t.gettext
    except Exception:
        return gettext.gettext # Fallback to default if translation not found

@app.middleware("http")
async def add_i18n_context(request: Request, call_next):
    request.state.gettext = get_translator(request)
    request.state.locale = get_locale_negotiator(request)
    response = await call_next(request)
    return response

@app.get("/set_language/{lang}")
async def set_language(lang: str, response: Response):
    if lang in LANGUAGES:
        response.set_cookie(key="lang", value=lang, httponly=True, expires=datetime.utcnow() + timedelta(days=30))
    return RedirectResponse(url="/")

# --- Jinja2 Filters ---
@templates.env.filter()
def datetimeformat(value, format='medium', locale='en'):
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if format == 'full':
        format = "EEEE, d. MMMM yyyy HH:mm"
    elif format == 'medium':
        format = "EEE, dd MMM yyyy HH:mm"
    return format_datetime(value, format=format, locale=locale)

@templates.env.filter()
def dateformat(value, format='medium', locale='en'):
    if isinstance(value, str):
        value = date.fromisoformat(value)
    if format == 'full':
        format = "EEEE, d. MMMM yyyy"
    elif format == 'medium':
        format = "EEE, dd MMM yyyy"
    return format_date(value, format=format, locale=locale)

@templates.env.filter()
def timeformat(value, format='short', locale='en'):
    if isinstance(value, str):
        value = time.fromisoformat(value)
    if format == 'full':
        format = "HH:mm:ss zzzz"
    elif format == 'medium':
        format = "HH:mm:ss"
    elif format == 'short':
        format = "HH:mm"
    return format_time(value, format=format, locale=locale)

@templates.env.filter()
def currencyformat(value, currency='USD', locale='en'):
    return format_currency(value, currency, locale=locale)

# --- Helper Functions ---
def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- Health Check ---
@app.get("/health")
def health_check():
    return {"status": "ok", "message": "BookSlot service is running!"}

# --- Owner Authentication & Registration ---
@router.post("/token", response_model=schemas.Token)
async def login_for_access_token(request: Request, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    owner = security.authenticate_owner(db, form_data.username, form_data.password, request.client.host)
    if not owner:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": str(owner.id)}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/register", response_model=schemas.Owner)
def register_owner(request: Request, owner: schemas.OwnerCreate, db: Session = Depends(get_db)):
    db_owner = crud.get_owner_by_email(db, email=owner.email)
    if db_owner:
        security_logger.warning(
            "OWNER_REGISTER_FAILED: Email already registered",
            extra={"client_ip": request.client.host, "username": owner.email}
        )
        raise HTTPException(status_code=400, detail="Email already registered")
    new_owner = crud.create_owner(db=db, owner=owner)
    security_logger.info(
        "OWNER_REGISTER_SUCCESS",
        extra={"client_ip": request.client.host, "username": owner.email}
    )
    return new_owner

# --- Customer Authentication & Registration ---
@router.post("/customer/token", response_model=schemas.Token)
async def customer_login_for_access_token(request: Request, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    customer = security.authenticate_customer(db, form_data.username, form_data.password, request.client.host)
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": str(customer.id)}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/customer/register", response_model=schemas.Customer)
def register_customer(request: Request, customer: schemas.CustomerCreate, db: Session = Depends(get_db)):
    db_customer = crud.get_customer_by_email(db, email=customer.email)
    if db_customer:
        security_logger.warning(
            "CUSTOMER_REGISTER_FAILED: Email already registered",
            extra={"client_ip": request.client.host, "username": customer.email}
        )
        raise HTTPException(status_code=400, detail="Email already registered")
    new_customer = crud.create_customer(db=db, customer=customer)
    security_logger.info(
        "CUSTOMER_REGISTER_SUCCESS",
        extra={"client_ip": request.client.host, "username": customer.email}
    )
    return new_customer

# --- Owner Dashboard ---
@router.get("/dashboard", response_class=HTMLResponse)
async def owner_dashboard(request: Request, db: Session = Depends(get_db), current_owner: models.Owner = Depends(security.get_current_owner)):
    _ = request.state.gettext
    locale = request.state.locale
    owner_services = crud.get_owner_services(db, owner_id=current_owner.id)
    
    # Fetch upcoming bookings
    upcoming_bookings = crud.get_upcoming_owner_bookings(db, owner_id=current_owner.id)

    # Fetch analytics data
    monthly_bookings = analytics.get_monthly_bookings_data(db, owner_id=current_owner.id)
    popular_services = analytics.get_popular_services_data(db, owner_id=current_owner.id)

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "owner": current_owner,
            "services": owner_services,
            "upcoming_bookings": upcoming_bookings,
            "monthly_bookings": monthly_bookings,
            "popular_services": popular_services,
            "_": _,
            "locale": locale,
            "lang_options": LANGUAGES
        }
    )

@router.post("/dashboard/profile", response_model=schemas.Owner)
async def update_owner_profile(request: Request, owner_update: schemas.OwnerUpdate, db: Session = Depends(get_db), current_owner: models.Owner = Depends(security.get_current_owner)):
    try:
        updated_owner = crud.update_owner(db, current_owner.id, owner_update)
        security_logger.info(
            "OWNER_PROFILE_UPDATE_SUCCESS",
            extra={"client_ip": request.client.host, "username": current_owner.email}
        )
        return updated_owner
    except Exception as e:
        security_logger.error(
            f"OWNER_PROFILE_UPDATE_FAILED: {e}",
            extra={"client_ip": request.client.host, "username": current_owner.email}
        )
        raise HTTPException(status_code=400, detail=str(e))

# --- Service Management ---
@router.post("/services", response_model=schemas.Service)
def create_service(request: Request, service: schemas.ServiceCreate, db: Session = Depends(get_db), current_owner: models.Owner = Depends(security.get_current_owner)):
    return crud.create_owner_service(db=db, service=service, owner_id=current_owner.id)

# --- Availability Management ---
@router.post("/availability", response_model=schemas.Availability)
def create_availability(request: Request, availability: schemas.AvailabilityCreate, db: Session = Depends(get_db), current_owner: models.Owner = Depends(security.get_current_owner)):
    return crud.create_owner_availability(db=db, availability=availability, owner_id=current_owner.id)

# --- Public Booking Page ---
@router.get("/book/{owner_username}", response_class=HTMLResponse)
async def booking_page(request: Request, owner_username: str, db: Session = Depends(get_db), service_id: Optional[int] = None):
    _ = request.state.gettext
    locale = request.state.locale
    owner = crud.get_owner_by_username(db, username=owner_username)
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")

    services = crud.get_owner_services(db, owner_id=owner.id)
    selected_service = None
    if service_id:
        selected_service = crud.get_service(db, service_id=service_id)
        if not selected_service or selected_service.owner_id != owner.id:
            selected_service = None # Ensure service belongs to owner

    return templates.TemplateResponse(
        "booking_page.html",
        {
            "request": request,
            "owner": owner,
            "services": services,
            "selected_service": selected_service,
            "_": _,
            "locale": locale,
            "lang_options": LANGUAGES
        }
    )

@router.post("/book/{owner_username}/submit", response_class=HTMLResponse)
async def submit_booking(request: Request, owner_username: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    _ = request.state.gettext
    locale = request.state.locale

    owner = crud.get_owner_by_username(db, username=owner_username)
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")

    form = await request.form()
    try:
        customer_name = form.get("customer_name")
        customer_email = form.get("customer_email")
        customer_phone = form.get("customer_phone")
        service_id = int(form.get("service_id"))
        booking_date_str = form.get("booking_date")
        booking_time_str = form.get("booking_time")
        is_recurring = form.get("is_recurring") == "on"
        recurrence_type = form.get("recurrence_type")
        recurrence_value = form.get("recurrence_value")
        recurrence_end_date_str = form.get("recurrence_end_date")

        if not all([customer_name, customer_email, service_id, booking_date_str, booking_time_str]):
            raise ValueError(_("All required booking fields must be filled."))

        booking_date = datetime.strptime(booking_date_str, "%Y-%m-%d").date()
        booking_time = datetime.strptime(booking_time_str, "%H:%M").time()

        # Get service duration
        service = crud.get_service(db, service_id=service_id)
        if not service or service.owner_id != owner.id:
            raise HTTPException(status_code=404, detail=_("Service not found or does not belong to this owner."))

        # Check availability
        available_slots = availability_utils.get_available_slots_for_day(
            db, owner.id, service_id, booking_date, service.duration_minutes
        )
        if booking_time not in available_slots:
            raise HTTPException(status_code=400, detail=_("Selected time slot is not available."))

        # Create booking(s)
        if is_recurring:
            recurrence_end_date = datetime.strptime(recurrence_end_date_str, "%Y-%m-%d").date() if recurrence_end_date_str else None
            booking_schema = schemas.RecurringBookingCreate(
                customer_name=customer_name,
                customer_email=customer_email,
                customer_phone=customer_phone,
                service_id=service_id,
                date=booking_date,
                time=booking_time,
                owner_id=owner.id,
                recurrence_type=schemas.RecurrenceType(recurrence_type) if recurrence_type else None,
                recurrence_value=recurrence_value,
                recurrence_end_date=recurrence_end_date
            )
            bookings = crud.create_recurring_booking(db, booking_schema)
            booking_ids = [str(b.id) for b in bookings]
            app_logger.info(f"Recurring booking created for owner {owner.id}, service {service_id}, bookings: {booking_ids}")
        else:
            booking_schema = schemas.BookingCreate(
                customer_name=customer_name,
                customer_email=customer_email,
                customer_phone=customer_phone,
                service_id=service_id,
                date=booking_date,
                time=booking_time,
                owner_id=owner.id
            )
            booking = crud.create_booking(db, booking_schema)
            booking_ids = [str(booking.id)]
            app_logger.info(f"Single booking created for owner {owner.id}, service {service_id}, booking: {booking.id}")

        # Send notifications in background
        background_tasks.add_task(notifications.send_booking_confirmation_emails, owner, booking_schema, service)
        if owner.phone_number:
             background_tasks.add_task(notifications.send_booking_confirmation_sms, owner, booking_schema, service)

        return templates.TemplateResponse(
            "booking_confirmation.html",
            {
                "request": request,
                "owner": owner,
                "booking_details": booking_schema, # Use schema for display
                "service": service,
                "_": _,
                "locale": locale
            }
        )
    except ValueError as e:
        app_logger.error(f"Booking submission ValueError: {e}", exc_info=True)
        return templates.TemplateResponse(
            "booking_page.html",
            {
                "request": request,
                "owner": owner,
                "services": crud.get_owner_services(db, owner_id=owner.id),
                "selected_service": service,
                "error_message": str(e),
                "_": _,
                "locale": locale
            },
            status_code=400
        )
    except HTTPException as e:
        app_logger.error(f"Booking submission HTTPException: {e.detail}", exc_info=True)
        return templates.TemplateResponse(
            "booking_page.html",
            {
                "request": request,
                "owner": owner,
                "services": crud.get_owner_services(db, owner_id=owner.id),
                "selected_service": service,
                "error_message": e.detail,
                "_": _,
                "locale": locale
            },
            status_code=e.status_code
        )
    except Exception as e:
        app_logger.critical(f"Critical error during booking submission: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=_("An unexpected error occurred. Please try again later."))


# --- Stripe Webhook ---
@app.post("/stripe-webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get('stripe-signature')

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError as e:
        # Invalid payload
        security_logger.warning(f"STRIPE_WEBHOOK_INVALID_PAYLOAD: {e}", extra={"client_ip": request.client.host})
        raise HTTPException(status_code=400, detail=str(e))
    except stripe.error.SignatureVerificationError as e:
        # Invalid signature
        security_logger.warning(f"STRIPE_WEBHOOK_INVALID_SIGNATURE: {e}", extra={"client_ip": request.client.host})
        raise HTTPException(status_code=400, detail=str(e))

    # Handle the event
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        owner_id = session.metadata.get('owner_id')
        if owner_id:
            crud.update_owner_subscription(db, int(owner_id), session.customer, session.subscription)
            app_logger.info(f"Stripe checkout session completed for owner {owner_id}. Customer: {session.customer}, Subscription: {session.subscription}")
            security_logger.info("OWNER_SUBSCRIPTION_UPDATE_SUCCESS", extra={"client_ip": request.client.host, "username": owner_id})
    # ... handle other event types as needed

    return {"status": "success"}


# --- Admin Panel (Simplified) ---
@router.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request, db: Session = Depends(get_db), current_owner: models.Owner = Depends(security.get_current_owner)): # Assuming only owners can be admins for now
    _ = request.state.gettext
    locale = request.state.locale
    if not current_owner.is_admin: # Placeholder for actual admin check
        security_logger.warning(
            "ADMIN_ACCESS_DENIED",
            extra={"client_ip": request.client.host, "username": current_owner.email}
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to access admin panel")
    
    owners = crud.get_owners(db)
    return templates.TemplateResponse(
        "admin_dashboard.html",
        {
            "request": request,
            "current_owner": current_owner,
            "owners": owners,
            "_": _,
            "locale": locale,
            "lang_options": LANGUAGES
        }
    )

@router.delete("/admin/owners/{owner_id}")
def delete_owner_admin(request: Request, owner_id: int, db: Session = Depends(get_db), current_owner: models.Owner = Depends(security.get_current_owner)):
    if not current_owner.is_admin:
        security_logger.warning(
            "ADMIN_DELETE_OWNER_DENIED",
            extra={"client_ip": request.client.host, "username": current_owner.email}
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
    crud.delete_owner(db, owner_id)
    security_logger.info(
        f"ADMIN_DELETE_OWNER_SUCCESS: {owner_id}",
        extra={"client_ip": request.client.host, "username": current_owner.email}
    )
    return {"message": "Owner deleted successfully"}

# Mount the router
app.include_router(router)
