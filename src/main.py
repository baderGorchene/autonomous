from fastapi import FastAPI, Depends, HTTPException, status, Request, Response, Form
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from starlette.middleware.sessions import SessionMiddleware
from typing import List, Optional, Dict, Any
from datetime import datetime, date, time, timedelta
import uuid # For recurrence_id
import json
import stripe
from gettext import gettext as _
from gettext import translation, bindtextdomain, textdomain
import os

from . import models, schemas, crud, security, notifications, analytics, availability_utils
from .database import SessionLocal, engine
from .config import settings

# Initialize DB
models.Base.metadata.create_all(bind=engine)

app = FastAPI()

# Add Session Middleware for i18n and other session management
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

# Initialize Stripe
stripe.api_key = settings.STRIPE_API_KEY

# Templates
templates = Jinja2Templates(directory="templates")

# i18n setup
LOCALE_DIR = "locales"
bindtextdomain("messages", LOCALE_DIR)
textdomain("messages")

@app.middleware("http")
async def add_i18n_middleware(request: Request, call_next):
    locale = request.session.get("locale", "en")
    
    if request.method == "GET" and "lang" in request.query_params:
        locale = request.query_params["lang"]
        request.session["locale"] = locale

    if locale not in ["en", "ar", "fr"]:
        locale = "en" # Fallback

    request.state.locale = locale
    trans = translation("messages", LOCALE_DIR, languages=[locale])
    request.state.gettext = trans.gettext
    
    response = await call_next(request)
    return response

@app.get("/lang/{locale_code}")
async def set_language(locale_code: str, request: Request):
    if locale_code in ["en", "ar", "fr"]:
        request.session["locale"] = locale_code
    return RedirectResponse(request.headers.get("referer", "/"))


# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Dependency for current owner (authenticated routes)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

async def get_current_owner(request: Request, db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = security.decode_access_token(token)
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
        token_data = schemas.TokenData(email=email)
    except Exception:
        raise credentials_exception
    owner = crud.get_owner_by_email(db, email=token_data.email)
    if owner is None:
        raise credentials_exception
    return owner

# Helper to get or create a customer (NEW)
def get_or_create_customer(db: Session, owner_id: int, customer_data: schemas.CustomerCreate) -> models.Customer:
    # Try to find existing customer by email and owner_id
    customer = db.query(models.Customer).filter(
        models.Customer.owner_id == owner_id,
        models.Customer.email == customer_data.email
    ).first()

    if customer:
        # If found, update name if it changed (optional, but good for data consistency)
        if customer.name != customer_data.name:
            customer.name = customer_data.name
            db.add(customer)
            db.commit()
            db.refresh(customer)
        return customer
    
    # If not found, create a new one
    db_customer = models.Customer(
        owner_id=owner_id,
        name=customer_data.name,
        email=customer_data.email,
        phone_number=customer_data.phone_number
    )
    db.add(db_customer)
    db.commit()
    db.refresh(db_customer)
    return db_customer

# --- Public Booking Page Routes ---
@app.get("/book/{owner_name_slug}", response_class=HTMLResponse)
async def booking_page(owner_name_slug: str, request: Request, db: Session = Depends(get_db)):
    owner = db.query(models.Owner).filter(func.lower(models.Owner.name) == func.lower(owner_name_slug)).first()
    if not owner:
        raise HTTPException(status_code=404, detail=request.state.gettext("Owner not found"))

    services = crud.get_owner_services(db, owner_id=owner.id)

    _ = request.state.gettext
    
    return templates.TemplateResponse(
        "booking_page.html",
        {
            "request": request,
            "owner": owner,
            "services": services,
            "current_date": date.today(),
            "gettext": _
        }
    )

@app.post("/book/submit", response_class=HTMLResponse)
async def submit_booking(
    request: Request,
    db: Session = Depends(get_db),
    owner_id: int = Form(...),
    service_id: int = Form(...),
    booking_date: date = Form(..., alias="date"),
    booking_time: time = Form(..., alias="time"),
    customer_name: str = Form(..., alias="name"),
    customer_email: EmailStr = Form(..., alias="email"),
    customer_phone: Optional[str] = Form(None, alias="phone"),
    is_recurring: bool = Form(False),
    recurrence_end_date: Optional[date] = Form(None)
):
    _ = request.state.gettext
    owner = crud.get_owner(db, owner_id=owner_id)
    service = crud.get_service(db, service_id=service_id)

    if not owner or not service:
        raise HTTPException(status_code=404, detail=_("Owner or Service not found"))

    slot_duration = service.duration_minutes
    available_slots = availability_utils.get_available_slots_for_day(db, owner.id, service.id, booking_date, slot_duration)

    if booking_time not in available_slots:
        raise HTTPException(status_code=400, detail=_("Selected time slot is not available. Please choose another time."))

    # Get or Create Customer (NEW LOGIC)
    customer_data = schemas.CustomerCreate(
        name=customer_name,
        email=customer_email,
        phone_number=customer_phone
    )
    customer = get_or_create_customer(db, owner.id, customer_data)

    # Create booking(s)
    if is_recurring and recurrence_end_date:
        recurrence_id = str(uuid.uuid4())
        current_booking_date = booking_date
        created_bookings_count = 0
        while current_booking_date <= recurrence_end_date:
            if booking_time in availability_utils.get_available_slots_for_day(db, owner.id, service.id, current_booking_date, slot_duration):
                booking_in = schemas.BookingCreate(
                    owner_id=owner.id,
                    service_id=service.id,
                    customer_id=customer.id, # NEW: Link to customer
                    date=current_booking_date,
                    time=booking_time,
                    is_confirmed=True,
                    recurrence_id=recurrence_id
                )
                crud.create_booking(db, booking_in)
                created_bookings_count += 1
            current_booking_date += timedelta(weeks=1) # Example: assuming weekly recurrence

        if created_bookings_count == 0:
            raise HTTPException(status_code=400, detail=_("No slots were available for the recurring booking period."))
        
        confirmation_message = _("Recurring booking(s) successfully created!")
    else:
        booking_in = schemas.BookingCreate(
            owner_id=owner.id,
            service_id=service.id,
            customer_id=customer.id, # NEW: Link to customer
            date=booking_date,
            time=booking_time,
            is_confirmed=True
        )
        db_booking = crud.create_booking(db, booking_in)
        confirmation_message = _("Your booking has been successfully created!")
        
    # Send notifications
    notifications.send_owner_booking_notification(owner, service, booking_date, booking_time, customer) # NEW: Pass customer object
    notifications.send_customer_booking_confirmation(owner, service, booking_date, booking_time, customer) # NEW: Pass customer object

    # Redirect to confirmation page
    return templates.TemplateResponse(
        "booking_confirmation.html",
        {
            "request": request,
            "owner_name": owner.name,
            "confirmation_message": confirmation_message,
            "gettext": _
        }
    )

# --- Owner Dashboard Routes ---
@app.get("/dashboard", response_class=HTMLResponse)
async def owner_dashboard(request: Request, db: Session = Depends(get_db), current_owner: models.Owner = Depends(get_current_owner)):
    _ = request.state.gettext

    upcoming_bookings = db.query(models.Booking).options(
        joinedload(models.Booking.service),
        joinedload(models.Booking.customer) # NEW: Load customer details
    ).filter(
        models.Booking.owner_id == current_owner.id,
        models.Booking.date >= date.today()
    ).order_by(
        models.Booking.date, models.Booking.time
    ).all()

    # Analytics data
    monthly_bookings = analytics.get_monthly_bookings_data(db, current_owner.id)
    popular_services = analytics.get_popular_services_data(db, current_owner.id)

    subscription_status = schemas.SubscriptionStatus(
        is_premium=current_owner.is_premium,
        current_plan="Premium" if current_owner.is_premium else "Free",
        subscription_active=current_owner.is_premium
    )

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "owner": current_owner,
            "upcoming_bookings": upcoming_bookings,
            "monthly_bookings": monthly_bookings,
            "popular_services": popular_services,
            "subscription_status": subscription_status,
            "gettext": _
        }
    )

# Placeholder for other routes like /login, /register, /services, /availabilities, /profile, /checkout, /webhook, etc.
# These would exist in a full app but are omitted for brevity as they are not directly modified by this task.
