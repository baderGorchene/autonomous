from fastapi import FastAPI, Depends, HTTPException, status, Request, Response
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta, date, datetime
from typing import List, Optional, Annotated
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.cors import CORSMiddleware
from gettext import gettext as _
import gettext
import os
import pytz
import uuid
import logging
import calendar
import stripe

from . import models, schemas, security, database, notifications, availability_utils, analytics
from .config import settings

from fastapi_limiter import FastAPILimiter
from fastapi_limiter.depends import RateLimiter
import redis.asyncio as redis

app = FastAPI()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

LOCALE_DIR = "locales"
LANGUAGES = {"en": "English", "ar": "العربية", "fr": "Français"}

def get_locale_negotiator(request: Request):
    lang_code = request.session.get("lang_code", "en")
    return gettext.translation('messages', LOCALE_DIR, languages=[lang_code], fallback=True)

@app.on_event("startup")
async def startup():
    redis_connection = redis.from_url(settings.REDIS_URL, encoding="utf8", decode_responses=True)
    await FastAPILimiter.init(redis_connection)
    
    models.Base.metadata.create_all(bind=database.engine)

@app.middleware("http")
async def add_i18n_context(request: Request, call_next):
    g = get_locale_negotiator(request)
    request.state.gettext = g.gettext
    response = await call_next(request)
    return response

@app.get("/change-language/{lang_code}", response_class=RedirectResponse)
async def change_language(lang_code: str, request: Request):
    if lang_code in LANGUAGES:
        request.session["lang_code"] = lang_code
    referer = request.headers.get("referer", "/")
    return RedirectResponse(url=referer)

def get_translator(request: Request):
    return request.state.gettext

def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.post("/token", response_model=schemas.Token)
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db),
    _ = Depends(get_translator)
):
    owner = db.query(models.Owner).filter(models.Owner.email == form_data.username).first()
    if not owner or not security.verify_password(form_data.password, owner.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_("Incorrect username or password"),
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": owner.email}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/owner/signup", response_model=schemas.OwnerInDB, dependencies=[Depends(RateLimiter(times=5, seconds=60))])
def create_owner(owner: schemas.OwnerCreate, db: Session = Depends(get_db), _ = Depends(get_translator)):
    db_owner = db.query(models.Owner).filter(models.Owner.email == owner.email).first()
    if db_owner:
        raise HTTPException(status_code=400, detail=_("Email already registered"))
    hashed_password = security.get_password_hash(owner.password)
    db_owner = models.Owner(email=owner.email, hashed_password=hashed_password, name=owner.name, phone=owner.phone, locale=owner.locale)
    db.add(db_owner)
    db.commit()
    db.refresh(db_owner)
    return db_owner

@app.post("/customer/signup", response_model=schemas.CustomerInDB, dependencies=[Depends(RateLimiter(times=5, seconds=60))])
def create_customer(customer: schemas.CustomerCreate, db: Session = Depends(get_db), _ = Depends(get_translator)):
    db_customer = db.query(models.Customer).filter(models.Customer.email == customer.email).first()
    if db_customer:
        raise HTTPException(status_code=400, detail=_("Email already registered"))
    hashed_password = security.get_password_hash(customer.password)
    db_customer = models.Customer(email=customer.email, hashed_password=hashed_password, name=customer.name, phone=customer.phone)
    db.add(db_customer)
    db.commit()
    db.refresh(db_customer)
    return db_customer

@app.post("/customer/token", response_model=schemas.Token)
async def login_for_customer_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db),
    _ = Depends(get_translator)
):
    customer = db.query(models.Customer).filter(models.Customer.email == form_data.username).first()
    if not customer or not security.verify_password(form_data.password, customer.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_("Incorrect username or password"),
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": customer.email, "role": "customer"}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/owner/me", response_model=schemas.Owner, dependencies=[Depends(RateLimiter(times=10, seconds=10))])
async def read_owner_me(current_owner: schemas.Owner = Depends(security.get_current_owner)):
    return current_owner

@app.put("/owner/me", response_model=schemas.Owner, dependencies=[Depends(RateLimiter(times=5, seconds=60))])
async def update_owner_profile(
    owner_update: schemas.OwnerUpdate,
    current_owner: models.Owner = Depends(security.get_current_owner),
    db: Session = Depends(get_db),
    _ = Depends(get_translator)
):
    for field, value in owner_update.dict(exclude_unset=True).items():
        setattr(current_owner, field, value)
    db.add(current_owner)
    db.commit()
    db.refresh(current_owner)
    return current_owner

@app.get("/owner/services", response_model=List[schemas.Service])
def read_owner_services(
    current_owner: models.Owner = Depends(security.get_current_owner),
    db: Session = Depends(get_db)
):
    return current_owner.services

@app.post("/owner/services", response_model=schemas.Service, status_code=status.HTTP_201_CREATED)
def create_owner_service(
    service: schemas.ServiceCreate,
    current_owner: models.Owner = Depends(security.get_current_owner),
    db: Session = Depends(get_db)
):
    db_service = models.Service(**service.dict(), owner_id=current_owner.id)
    db.add(db_service)
    db.commit()
    db.refresh(db_service)
    return db_service

@app.get("/bookslot/{owner_name}", response_class=HTMLResponse)
async def read_booking_page(owner_name: str, request: Request, db: Session = Depends(get_db), _ = Depends(get_translator)):
    owner = db.query(models.Owner).filter(models.Owner.name == owner_name).first()
    if not owner:
        raise HTTPException(status_code=404, detail=_("Owner not found"))
    services = db.query(models.Service).filter(models.Service.owner_id == owner.id).all()
    
    today = date.today()
    dates = [(today + timedelta(days=i)) for i in range(7)]

    return templates.TemplateResponse(
        "booking_page.html",
        {
            "request": request,
            "owner": owner,
            "services": services,
            "dates": dates,
            "lang": request.session.get("lang_code", "en"),
            "_": _,
            "get_current_year": datetime.now().year
        }
    )

@app.get("/api/services/{service_id}/available_slots", response_model=List[time])
async def get_available_slots(
    service_id: int,
    target_date: date,
    db: Session = Depends(get_db),
    _ = Depends(get_translator)
):
    service = db.query(models.Service).filter(models.Service.id == service_id).first()
    if not service:
        raise HTTPException(status_code=404, detail=_("Service not found"))
    
    available_slots = availability_utils.get_available_slots_for_day(
        db=db,
        owner_id=service.owner_id,
        service_id=service_id,
        target_date=target_date,
        slot_duration_minutes=service.duration_minutes
    )
    return available_slots

@app.post("/bookslot/submit_booking", response_model=schemas.Booking, dependencies=[Depends(RateLimiter(times=5, seconds=60))])
async def submit_booking(
    booking_data: schemas.BookingCreate, db: Session = Depends(get_db), _ = Depends(get_translator)
):
    service = db.query(models.Service).filter(models.Service.id == booking_data.service_id).first()
    if not service:
        raise HTTPException(status_code=404, detail=_("Service not found"))
    
    owner = db.query(models.Owner).filter(models.Owner.id == service.owner_id).first()
    if not owner:
        raise HTTPException(status_code=404, detail=_("Owner not found for service"))

    available_slots = availability_utils.get_available_slots_for_day(
        db=db,
        owner_id=owner.id,
        service_id=service.id,
        target_date=booking_data.date,
        slot_duration_minutes=service.duration_minutes
    )
    if booking_data.time not in available_slots:
        raise HTTPException(status_code=400, detail=_("Selected time slot is not available or already booked."))
    
    if booking_data.is_recurring:
        recurrence_id = str(uuid.uuid4())
        bookings_to_create = []
        current_date = booking_data.date
        while current_date <= booking_data.recurrence_end_date:
            daily_available_slots = availability_utils.get_available_slots_for_day(
                db=db,
                owner_id=owner.id,
                service_id=service.id,
                target_date=current_date,
                slot_duration_minutes=service.duration_minutes
            )
            if booking_data.time in daily_available_slots:
                bookings_to_create.append(models.Booking(
                    owner_id=owner.id,
                    service_id=service.id,
                    customer_name=booking_data.customer_name,
                    customer_email=booking_data.customer_email,
                    customer_phone=booking_data.customer_phone,
                    date=current_date,
                    time=booking_data.time,
                    is_recurring=True,
                    recurrence_id=recurrence_id,
                ))
            
            if booking_data.recurrence_type == models.RecurrenceType.DAILY:
                current_date += timedelta(days=1)
            elif booking_data.recurrence_type == models.RecurrenceType.WEEKLY:
                current_date += timedelta(weeks=1)
            elif booking_data.recurrence_type == models.RecurrenceType.MONTHLY:
                next_month = current_date.replace(day=1) + timedelta(days=32)
                current_date = next_month.replace(day=min(booking_data.date.day, calendar.monthrange(next_month.year, next_month.month)[1]))
            else:
                raise HTTPException(status_code=400, detail=_("Unsupported recurrence type."))
        
        if not bookings_to_create:
            raise HTTPException(status_code=400, detail=_("No available slots found for the recurring series."))

        first_booking = bookings_to_create[0]
        db.add(first_booking)
        db.commit()
        db.refresh(first_booking)

        for i in range(1, len(bookings_to_create)):
            bookings_to_create[i].parent_booking_id = first_booking.id
            db.add(bookings_to_create[i])
        db.commit()

        notifications.send_booking_confirmation(first_booking, service, owner)
        return first_booking
    
    else:
        db_booking = models.Booking(
            owner_id=owner.id,
            service_id=service.id,
            customer_name=booking_data.customer_name,
            customer_email=booking_data.customer_email,
            customer_phone=booking_data.customer_phone,
            date=booking_data.date,
            time=booking_data.time
        )
        db.add(db_booking)
        db.commit()
        db.refresh(db_booking)
        notifications.send_booking_confirmation(db_booking, service, owner)
        return db_booking

@app.post("/stripe-webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get('stripe-signature')

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError as e:
        logger.error(f"Stripe Webhook Error: Invalid payload: {e}")
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError as e:
        logger.error(f"Stripe Webhook Error: Invalid signature: {e}")
        raise HTTPException(status_code=400, detail="Invalid signature")

    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        customer_id = session.get('customer')
        subscription_id = session.get('subscription')
        owner_id = session.get('metadata', {}).get('owner_id')

        if owner_id and customer_id and subscription_id:
            owner = db.query(models.Owner).filter(models.Owner.id == owner_id).first()
            if owner:
                owner.stripe_customer_id = customer_id
                owner.stripe_subscription_id = subscription_id
                owner.subscription_status = models.SubscriptionStatus.ACTIVE
                db.add(owner)
                
                db_subscription = db.query(models.Subscription).filter(models.Subscription.owner_id == owner.id).first()
                if not db_subscription:
                    db_subscription = models.Subscription(owner_id=owner.id)
                
                db_subscription.stripe_customer_id = customer_id
                db_subscription.stripe_subscription_id = subscription_id
                db_subscription.status = models.SubscriptionStatus.ACTIVE
                
                db.add(db_subscription)
                db.commit()
                logger.info(f"Owner {owner_id} subscription activated.")
            else:
                logger.error(f"Owner {owner_id} not found for Stripe webhook event.")

    elif event['type'] == 'customer.subscription.updated' or event['type'] == 'customer.subscription.deleted':
        subscription_obj = event['data']['object']
        subscription_id = subscription_obj.get('id')
        status = subscription_obj.get('status')
        current_period_end = datetime.fromtimestamp(subscription_obj.get('current_period_end'), tz=pytz.utc) if subscription_obj.get('current_period_end') else None

        db_subscription = db.query(models.Subscription).filter(models.Subscription.stripe_subscription_id == subscription_id).first()
        if db_subscription:
            db_subscription.status = models.SubscriptionStatus(status)
            db_subscription.current_period_end = current_period_end
            db.add(db_subscription)
            db.commit()
            logger.info(f"Subscription {subscription_id} updated to status {status}.")
        else:
            logger.warning(f"Subscription {subscription_id} not found in DB for webhook update.")

    return Response(status_code=200)

@app.get("/admin/owners", response_model=List[schemas.Owner], dependencies=[Depends(security.get_current_admin_user)])
def get_all_owners(db: Session = Depends(get_db)):
    owners = db.query(models.Owner).all()
    return owners

@app.put("/admin/owners/{owner_id}", response_model=schemas.Owner, dependencies=[Depends(security.get_current_admin_user)])
def update_owner_by_admin(
    owner_id: int,
    owner_update: schemas.AdminOwnerUpdate,
    db: Session = Depends(get_db),
    _ = Depends(get_translator)
):
    owner = db.query(models.Owner).filter(models.Owner.id == owner_id).first()
    if not owner:
        raise HTTPException(status_code=404, detail=_("Owner not found"))
    
    for field, value in owner_update.dict(exclude_unset=True).items():
        if field == "subscription_status":
            setattr(owner, field, models.SubscriptionStatus(value))
        else:
            setattr(owner, field, value)
    
    db.add(owner)
    db.commit()
    db.refresh(owner)
    return owner

@app.get("/owner/analytics", response_model=schemas.DashboardAnalytics, dependencies=[Depends(RateLimiter(times=10, seconds=60))])
async def get_owner_analytics(
    current_owner: models.Owner = Depends(security.get_current_owner),
    db: Session = Depends(get_db)
):
    monthly_bookings = analytics.get_monthly_bookings_data(db, current_owner.id)
    popular_services = analytics.get_popular_services_data(db, current_owner.id)
    return schemas.DashboardAnalytics(
        monthly_bookings=monthly_bookings,
        popular_services=popular_services
    )