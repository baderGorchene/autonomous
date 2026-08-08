from fastapi import FastAPI, Depends, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta, date, datetime
import calendar
from typing import List, Annotated, Optional
import os
import gettext
import pytz

# Local imports
from src import models, schemas, security, notifications, stripe_utils
from src.database import SessionLocal, engine
from src.config import settings
from src.security import get_current_active_owner, create_access_token, authenticate_owner, get_password_hash
from src.notifications import send_booking_confirmation_email, send_booking_notification_whatsapp, send_booking_notification_email
from src.schemas import OwnerCreate, OwnerLogin, OwnerInDB, OwnerUpdate, ServiceCreate, Service, AvailabilityCreate, Availability, BookingCreate, Booking, BookingDisplay, CreateCheckoutSessionRequest, StripeWebhookEvent

# Template and i18n setup
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from starlette.background import BackgroundTasks

models.Base.metadata.create_all(bind=engine)

app = FastAPI()

app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

templates = Jinja2Templates(directory="src/templates")

locales_dir = settings.LOCALES_DIR

def get_locale(request: Request) -> str:
    lang = request.query_params.get("lang")
    if lang:
        request.session["lang"] = lang
        return lang
    
    if "lang" in request.session:
        return request.session["lang"]
    
    return settings.DEFAULT_LOCALE

@app.middleware("http")
async def add_i18n_middleware(request: Request, call_next):
    locale = get_locale(request)
    
    try:
        _ = gettext.translation('messages', locales_dir, languages=[locale], fallback=True).gettext
    except Exception as e:
        print(f"Error loading translation for locale {locale}: {e}. Falling back to default.")
        _ = gettext.translation('messages', locales_dir, languages=[settings.DEFAULT_LOCALE], fallback=True).gettext
    
    request.state.gettext = _
    response = await call_next(request)
    return response

@app.template_filter()
def _(text: str):
    return text

templates.env.filters['_'] = _

@app.template_filter()
def format_currency(value: int, locale: str = 'en'):
    amount = value / 100
    if locale == 'ar':
        return f"{amount:,.2f} ر.س"
    elif locale == 'fr':
        return f"{amount:,.2f} €"
    else:
        return f"${amount:,.2f}"

templates.env.filters['format_currency'] = format_currency
templates.env.filters['day_name'] = lambda d: calendar.day_name[d]

import stripe
stripe.api_key = settings.STRIPE_SECRET_KEY

@app.get("/health", response_class=HTMLResponse)
async def health_check():
    return "<h1>BookSlot is Healthy!</h1>"

@app.post("/token", response_model=schemas.Token)
async def login_for_access_token(form_data: Annotated[OAuth2PasswordRequestForm, Depends()], db: Session = Depends(get_db)):
    owner = authenticate_owner(db, form_data.username, form_data.password)
    if not owner:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": owner.email}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/signup", response_model=schemas.OwnerInDB, status_code=status.HTTP_201_CREATED)
async def create_owner(owner: OwnerCreate, db: Session = Depends(get_db)):
    db_owner = db.query(models.Owner).filter(models.Owner.email == owner.email).first()
    if db_owner:
        raise HTTPException(status_code=400, detail="Email already registered")
    hashed_password = get_password_hash(owner.password)
    db_owner = models.Owner(email=owner.email, hashed_password=hashed_password, full_name=owner.full_name, phone_number=owner.phone_number)
    db.add(db_owner)
    db.commit()
    db.refresh(db_owner)
    return db_owner

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db), current_owner: schemas.OwnerInDB = Depends(get_current_active_owner)):
    _ = request.state.gettext
    owner_services = db.query(models.Service).filter(models.Service.owner_id == current_owner.id).all()
    owner_availabilities = db.query(models.Availability).filter(models.Availability.owner_id == current_owner.id).all()

    now = datetime.utcnow()
    upcoming_bookings = (
        db.query(models.Booking, models.Service)
        .join(models.Service, models.Booking.service_id == models.Service.id)
        .filter(models.Booking.owner_id == current_owner.id)
        .filter(models.Booking.booking_date >= now.date())
        .order_by(models.Booking.booking_date, models.Booking.start_time)
        .all()
    )
    
    bookings_display = []
    for booking, service in upcoming_bookings:
        bookings_display.append(
            schemas.BookingDisplay(
                id=booking.id,
                customer_name=booking.customer_name,
                customer_email=booking.customer_email,
                customer_phone=booking.customer_phone,
                booking_date=booking.booking_date.strftime("%Y-%m-%d"),
                start_time=booking.start_time,
                end_time=booking.end_time,
                service_name=service.name,
                service_duration=service.duration_minutes,
                service_price=service.price / 100.0,
                status=booking.status,
                created_at=booking.created_at
            )
        )

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "owner": current_owner,
            "services": owner_services,
            "availabilities": owner_availabilities,
            "upcoming_bookings": bookings_display,
            "gettext": _,
            "current_locale": get_locale(request)
        }
    )

@app.put("/owner/profile", response_model=schemas.OwnerInDB)
async def update_owner_profile(
    owner_update: OwnerUpdate,
    db: Session = Depends(get_db),
    current_owner: schemas.OwnerInDB = Depends(get_current_active_owner)
):
    db_owner = db.query(models.Owner).filter(models.Owner.id == current_owner.id).first()
    if not db_owner:
        raise HTTPException(status_code=404, detail="Owner not found")

    if owner_update.full_name is not None:
        db_owner.full_name = owner_update.full_name
    if owner_update.phone_number is not None:
        db_owner.phone_number = owner_update.phone_number

    try:
        db.commit()
        db.refresh(db_owner)
        return db_owner
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update profile: {e}")

@app.post("/services/", response_model=schemas.Service, status_code=status.HTTP_201_CREATED)
async def create_service_for_owner(
    service: ServiceCreate,
    db: Session = Depends(get_db),
    current_owner: schemas.OwnerInDB = Depends(get_current_active_owner)
):
    db_service = models.Service(**service.dict(), owner_id=current_owner.id)
    db.add(db_service)
    db.commit()
    db.refresh(db_service)
    return db_service

@app.get("/services/", response_model=List[schemas.Service])
async def read_owner_services(
    db: Session = Depends(get_db),
    current_owner: schemas.OwnerInDB = Depends(get_current_active_owner)
):
    return db.query(models.Service).filter(models.Service.owner_id == current_owner.id).all()

@app.post("/availabilities/", response_model=schemas.Availability, status_code=status.HTTP_201_CREATED)
async def create_availability_for_owner(
    availability: AvailabilityCreate,
    db: Session = Depends(get_db),
    current_owner: schemas.OwnerInDB = Depends(get_current_active_owner)
):
    db_availability = models.Availability(**availability.dict(), owner_id=current_owner.id)
    db.add(db_availability)
    db.commit()
    db.refresh(db_availability)
    return db_availability

@app.get("/availabilities/", response_model=List[schemas.Availability])
async def read_owner_availabilities(
    db: Session = Depends(get_db),
    current_owner: schemas.OwnerInDB = Depends(get_current_active_owner)
):
    return db.query(models.Availability).filter(models.Availability.owner_id == current_owner.id).all()

@app.get("/bookslot.app/{owner_name}", response_class=HTMLResponse)
async def public_booking_page(owner_name: str, request: Request, db: Session = Depends(get_db)):
    _ = request.state.gettext
    owner = db.query(models.Owner).filter(models.Owner.full_name == owner_name).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")

    services = db.query(models.Service).filter(models.Service.owner_id == owner.id, models.Service.is_active == True).all()
    availabilities = db.query(models.Availability).filter(models.Availability.owner_id == owner.id).all()

    daily_slots = {i: [] for i in range(7)}
    for av in availabilities:
        daily_slots[av.day_of_week].append({"start": av.start_time, "end": av.end_time})

    return templates.TemplateResponse(
        "booking_page.html",
        {
            "request": request,
            "owner": owner,
            "services": services,
            "daily_slots": daily_slots,
            "gettext": _,
            "current_locale": get_locale(request)
        }
    )

@app.post("/bookslot.app/{owner_name}/book", response_model=schemas.Booking)
async def submit_booking(owner_name: str, booking_data: BookingCreate, background_tasks: BackgroundTasks, request: Request, db: Session = Depends(get_db)):
    _ = request.state.gettext
    owner = db.query(models.Owner).filter(models.Owner.full_name == owner_name).first()
    if not owner:
        raise HTTPException(status_code=404, detail=_("Owner not found."))

    service = db.query(models.Service).filter(models.Service.id == booking_data.service_id, models.Service.owner_id == owner.id).first()
    if not service:
        raise HTTPException(status_code=404, detail=_("Service not found for this owner."))

    booking_datetime_str = f"{booking_data.booking_date} {booking_data.start_time}"
    try:
        booking_dt = datetime.strptime(booking_datetime_str, "%Y-%m-%d %H:%M")
    except ValueError:
        raise HTTPException(status_code=400, detail=_("Invalid booking date or time format."))

    day_of_week = booking_dt.weekday()
    
    is_available = False
    availabilities = db.query(models.Availability).filter(
        models.Availability.owner_id == owner.id,
        models.Availability.day_of_week == day_of_week
    ).all()

    for av in availabilities:
        av_start = datetime.strptime(av.start_time, "%H:%M").time()
        av_end = datetime.strptime(av.end_time, "%H:%M").time()
        
        booking_time = booking_dt.time()
        
        if av_start <= booking_time < av_end:
            existing_booking = db.query(models.Booking).filter(
                models.Booking.owner_id == owner.id,
                models.Booking.booking_date == booking_dt.date(),
                models.Booking.start_time == booking_data.start_time,
                models.Booking.service_id == service.id
            ).first()
            
            if not existing_booking:
                is_available = True
                break
            else:
                raise HTTPException(status_code=409, detail=_("This time slot is already booked."))

    if not is_available:
        raise HTTPException(status_code=400, detail=_("Requested time slot is not available or outside working hours."))

    booking_start_dt = datetime.combine(booking_dt.date(), booking_dt.time())
    booking_end_dt = booking_start_dt + timedelta(minutes=service.duration_minutes)
    end_time_str = booking_end_dt.strftime("%H:%M")

    new_booking = models.Booking(
        owner_id=owner.id,
        service_id=service.id,
        customer_name=booking_data.customer_name,
        customer_email=booking_data.customer_email,
        customer_phone=booking_data.customer_phone,
        booking_date=booking_dt.date(),
        start_time=booking_data.start_time,
        end_time=end_time_str,
        status="confirmed"
    )
    db.add(new_booking)
    try:
        db.commit()
        db.refresh(new_booking)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=_("Failed to create booking due to a database error."))

    background_tasks.add_task(
        notifications.send_booking_confirmation_email,
        customer_email=new_booking.customer_email,
        owner_name=owner.full_name,
        service_name=service.name,
        booking_date=new_booking.booking_date.strftime("%Y-%m-%d"),
        booking_time=new_booking.start_time,
        locale=get_locale(request)
    )
    background_tasks.add_task(
        notifications.send_booking_notification_email,
        owner_email=owner.email,
        customer_name=new_booking.customer_name,
        service_name=service.name,
        booking_date=new_booking.booking_date.strftime("%Y-%m-%d"),
        booking_time=new_booking.start_time,
        locale=get_locale(request)
    )
    if owner.phone_number:
        background_tasks.add_task(
            notifications.send_booking_notification_whatsapp,
            owner_whatsapp_number=owner.phone_number,
            customer_name=new_booking.customer_name,
            service_name=service.name,
            booking_date=new_booking.booking_date.strftime("%Y-%m-%d"),
            booking_time=new_booking.start_time,
            locale=get_locale(request)
        )

    return new_booking

@app.get("/booking-confirmation", response_class=HTMLResponse)
async def booking_confirmation_page(request: Request):
    _ = request.state.gettext
    return templates.TemplateResponse(
        "booking_confirmation.html",
        {"request": request, "gettext": _, "current_locale": get_locale(request)}
    )

@app.post("/create-checkout-session")
async def create_checkout_session_endpoint(
    request: Request,
    db: Session = Depends(get_db),
    current_owner: schemas.OwnerInDB = Depends(get_current_active_owner)
):
    _ = request.state.gettext
    success_url = f"{settings.SERVER_NAME}/dashboard?payment_status=success&session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{settings.SERVER_NAME}/dashboard?payment_status=cancelled"

    try:
        checkout_session_url = stripe_utils.create_checkout_session(
            owner_id=current_owner.id,
            owner_email=current_owner.email,
            success_url=success_url,
            cancel_url=cancel_url
        )
        return {"url": checkout_session_url}
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=_("Failed to create Stripe checkout session."))

@app.post("/stripe-webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get('stripe-signature')

    event = stripe_utils.handle_webhook_event(payload, sig_header)

    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        owner_id = session.get('client_reference_id')
        customer_id = session.get('customer')
        
        if owner_id:
            db_owner = db.query(models.Owner).filter(models.Owner.id == int(owner_id)).first()
            if db_owner:
                db_owner.is_premium = True
                db_owner.stripe_customer_id = customer_id
                db.commit()
                db.refresh(db_owner)
                print(f"Owner {db_owner.email} upgraded to premium. Stripe Customer ID: {customer_id}")
            else:
                print(f"Owner with ID {owner_id} not found for webhook event.")
        else:
            print("No owner_id in client_reference_id for checkout.session.completed event.")
    
    elif event['type'] == 'invoice.payment_succeeded':
        invoice = event['data']['object']
        customer_id = invoice.get('customer')
        print(f"Recurring payment succeeded for customer {customer_id}")

    elif event['type'] == 'customer.subscription.deleted':
        subscription = event['data']['object']
        customer_id = subscription.get('customer')
        db_owner = db.query(models.Owner).filter(models.Owner.stripe_customer_id == customer_id).first()
        if db_owner:
            db_owner.is_premium = False
            db.commit()
            db.refresh(db_owner)
            print(f"Owner {db_owner.email} subscription cancelled.")
        else:
            print(f"Owner with Stripe Customer ID {customer_id} not found for subscription deleted event.")

    else:
        print(f"Unhandled event type {event['type']}")

    return Response(status_code=200)
