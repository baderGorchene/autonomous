from fastapi import FastAPI, Depends, HTTPException, status, Request, Form
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session, joinedload
from datetime import timedelta, date, datetime, time
from typing import List, Optional, Dict, Any
from jose import JWTError, jwt
from pydantic import ValidationError
from starlette.responses import HTMLResponse, RedirectResponse
from starlette.templating import Jinja2Templates
from starlette.staticfiles import StaticFiles
from pathlib import Path
from babel.dates import format_date, format_time
import gettext
import os
import calendar
import stripe

from . import models, schemas, security, notifications, config, analytics, availability_utils
from .database import SessionLocal, engine, Base

# Create database tables
Base.metadata.create_all(bind=engine)

app = FastAPI()

# Mount static files (CSS, JS, images)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Templates setup
templates = Jinja2Templates(directory="templates")

# Internationalization setup
LOCALE_DIR = Path("locales")
LANGUAGES = {"en": "English", "ar": "العربية", "fr": "Français"}

def get_locale(request: Request) -> str:
    lang = request.cookies.get("lang", "en")
    if lang not in LANGUAGES:
        lang = "en"
    return lang

def get_translator(request: Request):
    lang = get_locale(request)
    try:
        t = gettext.translation("messages", localedir=LOCALE_DIR, languages=[lang])
        t.install()
        return t.gettext
    except FileNotFoundError:
        return gettext.gettext

@app.middleware("http")
async def add_i18n_middleware(request: Request, call_next):
    request.state.gettext = get_translator(request)
    request.state.locale = get_locale(request)
    response = await call_next(request)
    return response

# Jinja2 i18n filter
def i18n_filter(text: str, request: Request, **kwargs):
    _ = request.state.gettext
    return _(text, **kwargs)

def format_date_filter(dt: date, request: Request, format: str = 'full'):
    locale = request.state.locale
    return format_date(dt, format=format, locale=locale)

def format_time_filter(t: time, request: Request, format: str = 'short'):
    locale = request.state.locale
    return format_time(t, format=format, locale=locale)

def format_currency_filter(amount: float, currency: str, request: Request):
    locale = request.state.locale
    if locale == 'ar':
        return f"{amount:,.2f} {currency}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{amount:,.2f} {currency}"

templates.env.filters["_"] = i18n_filter
templates.env.filters["format_date"] = format_date_filter
templates.env.filters["format_time"] = format_time_filter
templates.env.filters["format_currency"] = format_currency_filter

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# OAuth2PasswordBearer for token handling
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# --- Security & Authentication Dependencies ---
async def get_current_owner(request: Request, db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    token = request.cookies.get("access_token")
    if not token:
        raise credentials_exception
    return security.get_current_owner_from_token(token, db)

async def get_current_customer(request: Request, db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    token = request.cookies.get("customer_access_token")
    if not token:
        raise credentials_exception
    return security.get_current_customer_from_token(token, db)

# --- Root/Health Endpoint ---
@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.get("/set-language/{lang}")
async def set_language(lang: str, response: RedirectResponse, request: Request):
    if lang not in LANGUAGES:
        lang = "en"
    response.set_cookie(key="lang", value=lang, httponly=True, max_age=3600 * 24 * 30)
    referer = request.headers.get("referer", "/")
    response.headers["Location"] = referer
    return response

# --- Owner Authentication Endpoints ---
@app.post("/owners/signup", response_model=schemas.OwnerInDB)
def create_owner(owner: schemas.OwnerCreate, db: Session = Depends(get_db)):
    db_owner = security.get_owner_by_email(db, email=owner.email)
    if db_owner:
        raise HTTPException(status_code=400, detail="Email already registered")
    db_owner = security.get_owner_by_username(db, username=owner.username)
    if db_owner:
        raise HTTPException(status_code=400, detail="Username already registered")
    return security.create_owner(db=db, owner=owner)

@app.post("/owners/token", response_model=schemas.Token)
async def owner_login_for_access_token(response: HTMLResponse, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    owner = security.authenticate_owner(db, form_data.username, form_data.password)
    if not owner:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=config.settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": owner.username, "scope": "owner"}, expires_delta=access_token_expires
    )
    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    response.set_cookie(key="access_token", value=access_token, httponly=True, max_age=3600 * 24 * 7)
    return response

# --- Customer Authentication Endpoints ---
@app.post("/customers/signup", response_model=schemas.CustomerInDB)
def create_customer(customer: schemas.CustomerCreate, db: Session = Depends(get_db)):
    if not customer.password:
        raise HTTPException(status_code=400, detail="Password is required for customer account creation")
    db_customer = security.get_customer_by_email(db, email=customer.email)
    if db_customer:
        raise HTTPException(status_code=400, detail="Email already registered")
    return security.create_customer(db=db, customer=customer)

@app.post("/customers/token", response_model=schemas.Token)
async def customer_login_for_access_token(response: HTMLResponse, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    customer = security.authenticate_customer(db, form_data.username, form_data.password)
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=config.settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": customer.email, "scope": "customer"}, expires_delta=access_token_expires
    )
    response = RedirectResponse(url="/customer/dashboard", status_code=status.HTTP_302_FOUND)
    response.set_cookie(key="customer_access_token", value=access_token, httponly=True, max_age=3600 * 24 * 7)
    return response

# --- Owner Dashboard & Profile Endpoints ---
@app.get("/dashboard", response_class=HTMLResponse)
async def owner_dashboard(request: Request, db: Session = Depends(get_db), current_owner: models.Owner = Depends(get_current_owner)):
    _ = request.state.gettext
    bookings = db.query(models.Booking).filter(models.Booking.owner_id == current_owner.id).order_by(models.Booking.date, models.Booking.time).all()
    
    monthly_bookings = analytics.get_monthly_bookings_data(db, current_owner.id)
    popular_services = analytics.get_popular_services_data(db, current_owner.id)

    services = db.query(models.Service).filter(models.Service.owner_id == current_owner.id).all()

    subscription = db.query(models.Subscription).filter(models.Subscription.owner_id == current_owner.id).first()
    
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "owner": current_owner,
        "bookings": bookings,
        "monthly_bookings": monthly_bookings,
        "popular_services": popular_services,
        "services": services,
        "subscription": subscription,
        "languages": LANGUAGES,
        "current_lang": request.state.locale,
        "error_message": request.session.pop("error_message", None),
        "success_message": request.session.pop("success_message", None),
    })

@app.post("/owners/me", response_model=schemas.OwnerInDB)
def update_owner_profile(owner_update: schemas.OwnerUpdate, db: Session = Depends(get_db), current_owner: models.Owner = Depends(get_current_owner)):
    try:
        updated_owner = security.update_owner(db, current_owner, owner_update)
        return updated_owner
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

# --- Service Endpoints ---
@app.post("/owners/me/services", response_model=schemas.Service)
def create_service(service: schemas.ServiceCreate, db: Session = Depends(get_db), current_owner: models.Owner = Depends(get_current_owner)):
    db_service = models.Service(**service.dict(), owner_id=current_owner.id)
    db.add(db_service)
    db.commit()
    db.refresh(db_service)
    return db_service

@app.put("/owners/me/services/{service_id}", response_model=schemas.Service)
def update_service(service_id: int, service_update: schemas.ServiceUpdate, db: Session = Depends(get_db), current_owner: models.Owner = Depends(get_current_owner)):
    db_service = db.query(models.Service).filter(models.Service.id == service_id, models.Service.owner_id == current_owner.id).first()
    if not db_service:
        raise HTTPException(status_code=404, detail="Service not found")
    for key, value in service_update.dict(exclude_unset=True).items():
        setattr(db_service, key, value)
    db.commit()
    db.refresh(db_service)
    return db_service

# --- Availability Endpoints ---
@app.post("/owners/me/availabilities", response_model=schemas.Availability)
def create_availability(availability: schemas.AvailabilityCreate, db: Session = Depends(get_db), current_owner: models.Owner = Depends(get_current_owner)):
    db_availability = models.Availability(**availability.dict(), owner_id=current_owner.id)
    db.add(db_availability)
    db.commit()
    db.refresh(db_availability)
    return db_availability

# --- Public Booking Page Endpoints ---
@app.get("/book/{owner_username}", response_class=HTMLResponse)
async def booking_page(request: Request, owner_username: str, db: Session = Depends(get_db)):
    _ = request.state.gettext
    owner = db.query(models.Owner).filter(models.Owner.username == owner_username).first()
    if not owner:
        raise HTTPException(status_code=404, detail=_("Owner not found"))

    services = db.query(models.Service).filter(models.Service.owner_id == owner.id).all()
    
    today = date.today()
    available_dates_display = {}
    for i in range(2):
        month_start = date(today.year, today.month + i, 1) if today.month + i <= 12 else date(today.year + 1, today.month + i - 12, 1)
        num_days = calendar.monthrange(month_start.year, month_start.month)[1]
        for day in range(1, num_days + 1):
            current_date = date(month_start.year, month_start.month, day)
            if current_date >= today:
                available_dates_display[str(current_date)] = True

    return templates.TemplateResponse("booking_page.html", {
        "request": request,
        "owner": owner,
        "services": services,
        "available_dates": available_dates_display,
        "languages": LANGUAGES,
        "current_lang": request.state.locale,
        "error_message": request.session.pop("error_message", None),
        "success_message": request.session.pop("success_message", None),
    })

@app.get("/api/book/{owner_username}/services/{service_id}/available-slots")
async def get_available_slots_api(
    owner_username: str,
    service_id: int,
    target_date: date,
    db: Session = Depends(get_db)
) -> List[time]:
    owner = db.query(models.Owner).filter(models.Owner.username == owner_username).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")
    
    service = db.query(models.Service).filter(models.Service.id == service_id, models.Service.owner_id == owner.id).first()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found for this owner")

    available_slots = availability_utils.get_available_slots_for_day(
        db, owner.id, service.id, target_date, service.duration_minutes
    )
    return available_slots

@app.post("/book/{owner_username}/{service_id}/submit", response_class=HTMLResponse)
async def submit_booking(
    request: Request,
    owner_username: str,
    service_id: int,
    customer_name: str = Form(...),
    customer_email: EmailStr = Form(...),
    customer_phone: Optional[str] = Form(None),
    booking_date: date = Form(...),
    booking_time: time = Form(...),
    db: Session = Depends(get_db)
):
    _ = request.state.gettext
    owner = db.query(models.Owner).filter(models.Owner.username == owner_username).first()
    if not owner:
        raise HTTPException(status_code=404, detail=_("Owner not found"))

    service = db.query(models.Service).filter(models.Service.id == service_id, models.Service.owner_id == owner.id).first()
    if not service:
        raise HTTPException(status_code=404, detail=_("Service not found for this owner"))

    slot_duration = service.duration_minutes
    available_slots = availability_utils.get_available_slots_for_day(db, owner.id, service.id, booking_date, slot_duration)
    if booking_time not in available_slots:
        raise HTTPException(status_code=400, detail=_("Selected time slot is not available or already booked."))

    customer = db.query(models.Customer).filter(models.Customer.email == customer_email).first()
    if not customer:
        customer = models.Customer(email=customer_email, full_name=customer_name, phone_number=customer_phone)
        db.add(customer)
        db.commit()
        db.refresh(customer)
    elif customer.full_name != customer_name or customer.phone_number != customer_phone:
        customer.full_name = customer_name
        customer.phone_number = customer_phone
        db.add(customer)
        db.commit()
        db.refresh(customer)

    db_booking = models.Booking(
        owner_id=owner.id,
        service_id=service.id,
        customer_id=customer.id,
        customer_name=customer_name,
        customer_email=customer_email,
        customer_phone=customer_phone,
        date=booking_date,
        time=booking_time,
        is_confirmed=True
    )
    db.add(db_booking)
    db.commit()
    db.refresh(db_booking)

    notifications.send_booking_confirmation_email(customer_email, owner.email, service.name, booking_date, booking_time, owner.full_name)
    notifications.send_owner_booking_notification(owner.phone_number, service.name, booking_date, booking_time, customer_name, customer_phone)
    
    return templates.TemplateResponse("booking_confirmation.html", {
        "request": request,
        "booking": db_booking,
        "owner": owner,
        "service": service,
        "languages": LANGUAGES,
        "current_lang": request.state.locale,
    })

# --- Analytics API Endpoint (for dashboard) ---
@app.get("/api/owners/me/analytics/monthly-bookings", response_model=List[schemas.MonthlyBookingsData])
def get_owner_monthly_bookings(
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(get_current_owner)
):
    return analytics.get_monthly_bookings_data(db, current_owner.id)

@app.get("/api/owners/me/analytics/popular-services", response_model=List[schemas.PopularServiceData])
def get_owner_popular_services(
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(get_current_owner)
):
    return analytics.get_popular_services_data(db, current_owner.id)

# --- Stripe Webhook Endpoint ---
@app.post("/stripe-webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get('stripe-signature')

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, config.settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except stripe.error.SignatureVerificationError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        owner_id = session.metadata.get('owner_id')
        if owner_id:
            owner = db.query(models.Owner).filter(models.Owner.id == int(owner_id)).first()
            if owner:
                subscription = db.query(models.Subscription).filter(models.Subscription.owner_id == owner.id).first()
                if not subscription:
                    subscription = models.Subscription(owner_id=owner.id)
                    db.add(subscription)
                
                subscription.stripe_customer_id = session.customer
                subscription.stripe_subscription_id = session.subscription
                subscription.status = models.SubscriptionStatus.ACTIVE
                
                stripe_subscription = stripe.Subscription.retrieve(session.subscription)
                subscription.current_period_end = datetime.fromtimestamp(stripe_subscription.current_period_end)

                db.commit()
                db.refresh(subscription)
                print(f"Owner {owner.id} subscribed successfully.")
    elif event['type'] == 'invoice.payment_succeeded':
        invoice = event['data']['object']
        subscription_id = invoice.subscription
        stripe_subscription = stripe.Subscription.retrieve(subscription_id)
        
        db_subscription = db.query(models.Subscription).filter(models.Subscription.stripe_subscription_id == subscription_id).first()
        if db_subscription:
            db_subscription.status = models.SubscriptionStatus.ACTIVE
            db_subscription.current_period_end = datetime.fromtimestamp(stripe_subscription.current_period_end)
            db.commit()
            db.refresh(db_subscription)
            print(f"Subscription {subscription_id} renewed.")
    elif event['type'] == 'customer.subscription.deleted':
        subscription_obj = event['data']['object']
        db_subscription = db.query(models.Subscription).filter(models.Subscription.stripe_subscription_id == subscription_obj.id).first()
        if db_subscription:
            db_subscription.status = models.SubscriptionStatus.CANCELED
            db.commit()
            db.refresh(db_subscription)
            print(f"Subscription {subscription_obj.id} canceled.")
    
    return {"status": "success"}

@app.post("/create-checkout-session")
async def create_checkout_session(request: Request, current_owner: models.Owner = Depends(get_current_owner)):
    try:
        checkout_session = stripe.checkout.Session.create(
            line_items=[
                {
                    'price': config.settings.STRIPE_PREMIUM_PRICE_ID,
                    'quantity': 1,
                },
            ],
            mode='subscription',
            success_url=request.url_for('owner_dashboard').path + "?success=true",
            cancel_url=request.url_for('owner_dashboard').path + "?canceled=true",
            metadata={
                'owner_id': str(current_owner.id)
            }
        )
        return {"url": checkout_session.url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- Review Endpoints (NEW) ---
@app.post("/services/{service_id}/reviews", response_model=schemas.Review)
async def submit_review_for_service(
    service_id: int,
    review_data: schemas.ReviewCreate,
    db: Session = Depends(get_db),
    current_customer: models.Customer = Depends(get_current_customer)
):
    service = db.query(models.Service).filter(models.Service.id == service_id).first()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")

    existing_booking = db.query(models.Booking).filter(
        models.Booking.service_id == service_id,
        models.Booking.customer_id == current_customer.id,
        models.Booking.date <= date.today()
    ).first()

    if not existing_booking:
        raise HTTPException(status_code=403, detail="You can only review services you have booked and completed.")

    existing_review = db.query(models.Review).filter(
        models.Review.service_id == service_id,
        models.Review.customer_id == current_customer.id
    ).first()
    if existing_review:
        raise HTTPException(status_code=400, detail="You have already submitted a review for this service.")

    db_review = models.Review(
        service_id=service_id,
        customer_id=current_customer.id,
        owner_id=service.owner_id,
        rating=review_data.rating,
        comment=review_data.comment
    )
    db.add(db_review)
    db.commit()
    db.refresh(db_review)
    return db_review

@app.get("/services/{service_id}/reviews", response_model=List[schemas.Review])
async def get_reviews_for_service(
    service_id: int,
    db: Session = Depends(get_db)
):
    service = db.query(models.Service).filter(models.Service.id == service_id).first()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    
    reviews = db.query(models.Review).filter(models.Review.service_id == service_id).order_by(models.Review.created_at.desc()).all()
    return reviews

@app.get("/owners/me/reviews", response_model=List[schemas.Review])
async def get_reviews_for_owner_services(
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(get_current_owner)
):
    reviews = db.query(models.Review).filter(models.Review.owner_id == current_owner.id).order_by(models.Review.created_at.desc()).all()
    return reviews