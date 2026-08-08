from fastapi import FastAPI, Depends, HTTPException, status, Request, Form, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import func, extract, and_
from datetime import datetime, timedelta, date, time
from typing import List, Annotated, Optional
from babel.dates import format_currency
import json
import gettext
import os
import locale as sys_locale # To set system locale for babel

from . import models, schemas, security, notifications
from .database import SessionLocal, engine
from .config import settings

# Stripe imports
import stripe

# Initialize Stripe
stripe.api_key = settings.STRIPE_SECRET_KEY

models.Base.metadata.create_all(bind=engine)

app = FastAPI()

# Setup templates and static files
templates = Jinja2Templates(directory="src/templates")
app.mount("/static", StaticFiles(directory="src/static"), name="static")
app.mount("/locales", StaticFiles(directory=settings.LOCALES_DIR), name="locales")

# OAuth2 setup
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Dependency to get current owner
async def get_current_owner(token: Annotated[str, Depends(oauth2_scheme)], db: Session = Depends(get_db)):
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
    owner = db.query(models.Owner).filter(models.Owner.email == token_data.email).first()
    if owner is None:
        raise credentials_exception
    return owner

# Internationalization setup
def get_locale(request: Request) -> str:
    # Priority: URL param > cookie > owner setting > default
    locale_param = request.query_params.get("lang")
    if locale_param in ["en", "ar", "fr"]:
        return locale_param
    
    locale_cookie = request.cookies.get("locale")
    if locale_cookie in ["en", "ar", "fr"]:
        return locale_cookie
        
    # If owner is logged in, use owner's locale. This requires current_owner dependency
    # For public pages, we can't rely on current_owner
    # For now, we'll just use the default if no param/cookie
    return settings.DEFAULT_LOCALE

@app.middleware("http")
async def add_i18n_middleware(request: Request, call_next):
    locale = get_locale(request)
    
    # Set the locale for gettext
    try:
        # For system-wide locale (e.g. for babel format_currency)
        # This might not be thread-safe in async environments, but generally works for simple cases
        sys_locale.setlocale(sys_locale.LC_ALL, f"{locale}_{locale.upper()}.UTF-8")
    except sys_locale.Error:
        # Fallback if locale not found on system
        sys_locale.setlocale(sys_locale.LC_ALL, 'C.UTF-8')

    lang_translation = gettext.translation('messages', localedir=settings.LOCALES_DIR, languages=[locale], fallback=True)
    request.state.gettext = lang_translation.gettext
    request.state.locale = locale
    response = await call_next(request)
    response.set_cookie(key="locale", value=locale, httponly=False, expires=3600*24*30) # 30 days
    return response

templates.env.globals['gettext'] = lambda s: s # Default for non-request context
templates.env.globals['ngettext'] = lambda s, p, n: s
templates.env.globals['locale'] = settings.DEFAULT_LOCALE

@app.get("/health")
async def health_check():
    return {"status": "ok"}

# --- Authentication Endpoints ---
@app.post("/owner/signup", response_model=schemas.Owner)
def create_owner(owner: schemas.OwnerCreate, db: Session = Depends(get_db)):
    db_owner = db.query(models.Owner).filter(models.Owner.email == owner.email).first()
    if db_owner:
        raise HTTPException(status_code=400, detail="Email already registered")
    hashed_password = security.get_password_hash(owner.password)
    db_owner = models.Owner(
        email=owner.email, 
        hashed_password=hashed_password, 
        name=owner.name, 
        phone=owner.phone,
        booking_page_slug=owner.booking_page_slug,
        locale=owner.locale or settings.DEFAULT_LOCALE
    )
    db.add(db_owner)
    db.commit()
    db.refresh(db_owner)
    return db_owner

@app.post("/token", response_model=schemas.Token)
def login_for_access_token(form_data: Annotated[OAuth2PasswordRequestForm, Depends()], db: Session = Depends(get_db)):
    owner = security.authenticate_owner(db, form_data.username, form_data.password)
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

# --- Owner Profile Endpoints ---
@app.get("/owner/me", response_model=schemas.Owner)
def read_owner_me(current_owner: Annotated[models.Owner, Depends(get_current_owner)]):
    return current_owner

@app.put("/owner/me", response_model=schemas.Owner)
def update_owner_me(
    owner_update: schemas.OwnerUpdate,
    current_owner: Annotated[models.Owner, Depends(get_current_owner)],
    db: Session = Depends(get_db)
):
    for field, value in owner_update.dict(exclude_unset=True).items():
        setattr(current_owner, field, value)
    db.commit()
    db.refresh(current_owner)
    return current_owner

# --- Service Endpoints ---
@app.post("/owner/services", response_model=schemas.Service)
def create_service_for_owner(
    service: schemas.ServiceCreate,
    current_owner: Annotated[models.Owner, Depends(get_current_owner)],
    db: Session = Depends(get_db)
):
    db_service = models.Service(**service.dict(), owner_id=current_owner.id)
    db.add(db_service)
    db.commit()
    db.refresh(db_service)
    return db_service

@app.get("/owner/services", response_model=List[schemas.Service])
def read_services_for_owner(
    current_owner: Annotated[models.Owner, Depends(get_current_owner)],
    db: Session = Depends(get_db)
):
    return current_owner.services

# --- Availability Endpoints (MODIFIED) ---
@app.post("/owner/availability", response_model=schemas.Availability)
def create_availability_for_owner(
    availability: schemas.AvailabilityCreate,
    current_owner: Annotated[models.Owner, Depends(get_current_owner)],
    db: Session = Depends(get_db)
):
    # Basic validation for time range and dates
    if availability.start_time_of_day >= availability.end_time_of_day:
        raise HTTPException(status_code=400, detail="End time must be after start time")
    if availability.end_date and availability.start_date > availability.end_date:
        raise HTTPException(status_code=400, detail="End date must be after start date")

    db_availability = models.Availability(
        start_time_of_day=availability.start_time_of_day,
        end_time_of_day=availability.end_time_of_day,
        rrule_string=availability.rrule_string,
        start_date=availability.start_date,
        end_date=availability.end_date,
        owner_id=current_owner.id
    )
    # Handle exception_dates property setter
    db_availability.exception_dates = availability.exception_dates or []

    db.add(db_availability)
    db.commit()
    db.refresh(db_availability)
    return db_availability

@app.get("/owner/availability", response_model=List[schemas.Availability])
def read_availability_for_owner(
    current_owner: Annotated[models.Owner, Depends(get_current_owner)],
    db: Session = Depends(get_db)
):
    return current_owner.availabilities

# --- Booking Endpoints ---
# Simplified /book/{owner_name} endpoint, assuming it fetches services and a way to book
@app.get("/book/{owner_slug}", response_class=HTMLResponse)
async def booking_page(owner_slug: str, request: Request, db: Session = Depends(get_db)):
    owner = db.query(models.Owner).filter(models.Owner.booking_page_slug == owner_slug).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")

    services = db.query(models.Service).filter(models.Service.owner_id == owner.id, models.Service.is_active == True).all()
    
    # For this step, we are not generating slots from the new availability model yet.
    # This will be part of the next task. For now, it might just display basic info or
    # assume simple pre-defined slots.
    
    _ = request.state.gettext
    return templates.TemplateResponse(
        "booking_page.html",
        {
            "request": request,
            "owner": owner,
            "services": services,
            "locale": request.state.locale,
            "_": _,
            "title": _("Book an Appointment with {owner_name}").format(owner_name=owner.name)
        }
    )

@app.post("/book/{owner_slug}/submit", response_model=schemas.BookingConfirmation)
async def submit_booking(
    owner_slug: str,
    booking_data: schemas.BookingCreate,
    request: Request,
    db: Session = Depends(get_db)
):
    owner = db.query(models.Owner).filter(models.Owner.booking_page_slug == owner_slug).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")
    
    service = db.query(models.Service).filter(
        models.Service.id == booking_data.service_id,
        models.Service.owner_id == owner.id
    ).first()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found or does not belong to this owner")

    # In a real scenario, check availability here using the new Availability model
    # For this task, we assume availability check is done at UI or simplified
    # This part will be heavily modified in the next task.
    
    end_time = booking_data.start_time + timedelta(minutes=service.duration_minutes)

    db_booking = models.Booking(
        owner_id=owner.id,
        service_id=service.id,
        customer_name=booking_data.customer_name,
        customer_email=booking_data.customer_email,
        customer_phone=booking_data.customer_phone,
        start_time=booking_data.start_time,
        end_time=end_time,
        status="confirmed"
    )
    db.add(db_booking)
    db.commit()
    db.refresh(db_booking)

    # Send notifications (simplified for this context)
    # notifications.send_email_confirmation(owner, db_booking, service, to_customer=True)
    # notifications.send_email_confirmation(owner, db_booking, service, to_customer=False)
    # notifications.send_whatsapp_notification(owner, db_booking, service)

    _ = request.state.gettext
    return schemas.BookingConfirmation(
        message=_("Booking confirmed successfully!"),
        booking_details=schemas.Booking.from_orm(db_booking)
    )

@app.get("/booking-confirmation", response_class=HTMLResponse)
async def booking_confirmation_page(request: Request):
    _ = request.state.gettext
    return templates.TemplateResponse(
        "booking_confirmation.html",
        {"request": request, "_": _}
    )
        
# --- Owner Dashboard Endpoints ---
@app.get("/dashboard", response_class=HTMLResponse)
async def owner_dashboard(
    request: Request,
    current_owner: Annotated[models.Owner, Depends(get_current_owner)],
    db: Session = Depends(get_db)
):
    _ = request.state.gettext
    
    # Fetch upcoming bookings
    now = datetime.now()
    upcoming_bookings = db.query(models.Booking).filter(
        models.Booking.owner_id == current_owner.id,
        models.Booking.start_time >= now
    ).order_by(models.Booking.start_time).all()

    # Fetch services
    services = db.query(models.Service).filter(models.Service.owner_id == current_owner.id).all()

    # Fetch analytics (simplified as per previous steps)
    # This should use the dedicated analytics endpoint or a service
    analytics = {
        "total_bookings_this_month": 0,
        "monthly_booking_counts": [],
        "popular_services": []
    }
    
    # For this task, we are not changing the dashboard UI for advanced availability setup yet.
    # This will be part of the next task.
    
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "owner": current_owner,
            "upcoming_bookings": upcoming_bookings,
            "services": services,
            "analytics": analytics,
            "locale": request.state.locale,
            "_": _,
            "format_currency": lambda value, currency: format_currency(value, currency, locale=request.state.locale)
        }
    )

# --- Stripe Webhook Endpoint ---
@app.post("/stripe-webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    event = None

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except stripe.error.SignatureVerificationError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Handle the event
    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        customer_id = session.get("customer")
        subscription_id = session.get("subscription")
        
        owner = db.query(models.Owner).filter(models.Owner.stripe_customer_id == customer_id).first()
        if owner:
            owner.stripe_subscription_id = subscription_id
            owner.subscription_status = "active"
            db.commit()
    elif event["type"] == "customer.subscription.updated":
        subscription = event["data"]["object"]
        owner = db.query(models.Owner).filter(models.Owner.stripe_subscription_id == subscription.id).first()
        if owner:
            owner.subscription_status = subscription.status # e.g., 'active', 'canceled', 'past_due'
            db.commit()
    elif event["type"] == "customer.subscription.deleted":
        subscription = event["data"]["object"]
        owner = db.query(models.Owner).filter(models.Owner.stripe_subscription_id == subscription.id).first()
        if owner:
            owner.subscription_status = "cancelled"
            owner.stripe_subscription_id = None # Optionally clear
            db.commit()
    
    return {"status": "success"}

# --- Admin Panel (Simplified) ---
# Placeholder for admin panel - actual implementation would require admin auth
@app.get("/admin/owners", response_model=List[schemas.Owner])
def admin_list_owners(db: Session = Depends(get_db)):
    # In a real app, this would require admin authentication
    return db.query(models.Owner).all()

# --- Analytics API Endpoint (as per previous steps) ---
@app.get("/api/owner/analytics", response_model=schemas.DashboardAnalytics)
def get_owner_analytics(
    current_owner: Annotated[models.Owner, Depends(get_current_owner)],
    db: Session = Depends(get_db)
):
    now = datetime.now()
    
    # Total bookings this month
    total_bookings_this_month = db.query(models.Booking).filter(
        models.Booking.owner_id == current_owner.id,
        extract('year', models.Booking.start_time) == now.year,
        extract('month', models.Booking.start_time) == now.month
    ).count()

    # Monthly booking counts for the last 6 months
    monthly_booking_counts = []
    for i in range(6):
        target_month = (now.replace(day=1) - timedelta(days=30*i)).month
        target_year = (now.replace(day=1) - timedelta(days=30*i)).year
        count = db.query(models.Booking).filter(
            models.Booking.owner_id == current_owner.id,
            extract('year', models.Booking.start_time) == target_year,
            extract('month', models.Booking.start_time) == target_month
        ).count()
        monthly_booking_counts.append(schemas.BookingCount(month=f"{target_year}-{target_month:02d}", count=count))
    monthly_booking_counts.reverse() # Show oldest first

    # Popular services
    popular_services = db.query(
        models.Service.name,
        func.count(models.Booking.id).label("booking_count")
    ).join(models.Booking).filter(
        models.Booking.owner_id == current_owner.id,
        models.Service.owner_id == current_owner.id # Ensure service belongs to owner
    ).group_by(models.Service.name).order_by(func.count(models.Booking.id).desc()).limit(5).all()

    popular_services_schemas = [
        schemas.PopularService(service_name=name, booking_count=count)
        for name, count in popular_services
    ]

    return schemas.DashboardAnalytics(
        total_bookings_this_month=total_bookings_this_month,
        monthly_booking_counts=monthly_booking_counts,
        popular_services=popular_services_schemas
    )
