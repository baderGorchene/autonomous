from fastapi import FastAPI, Depends, HTTPException, status, BackgroundTasks, Request, Response, Form
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, date, time
from typing import List, Optional, Dict, Any
from uuid import uuid4
import calendar
import os
import gettext
import json

from . import models, schemas, security, notifications
from .database import SessionLocal, engine
from .config import settings
from .stripe_utils import create_checkout_session, handle_webhook_event
from .analytics import get_monthly_booking_counts, get_popular_services

models.Base.metadata.create_all(bind=engine)

app = FastAPI()

locales_dir = settings.LOCALES_DIR
translations = {}
for lang in ['en', 'ar', 'fr']:
    try:
        lang_dir = os.path.join(locales_dir, lang, 'LC_MESSAGES')
        if os.path.exists(os.path.join(lang_dir, 'messages.mo')):
            t = gettext.translation('messages', locales_dir, languages=[lang])
            translations[lang] = t
        else:
            print(f"Warning: .mo file not found for {lang} in {lang_dir}")
    except Exception as e:
        print(f"Error loading translation for {lang}: {e}")
        translations[lang] = gettext.NullTranslations()

def get_locale_from_request(request: Request) -> str:
    lang = request.query_params.get("lang")
    if lang in translations:
        return lang
    lang = request.cookies.get("lang")
    if lang in translations:
        return lang
    accept_language = request.headers.get("accept-language", "")
    for lang_code in accept_language.split(','):
        lang_code = lang_code.split(';')[0].strip().lower()
        if lang_code.startswith('ar'):
            return 'ar'
        if lang_code.startswith('fr'):
            return 'fr'
        if lang_code.startswith('en'):
            return 'en'
    return settings.DEFAULT_LOCALE

def gettext_lazy(text: str, locale: str = None):
    def _inner(request: Request = None):
        if locale:
            t = translations.get(locale, translations['en'])
        else:
            current_locale = get_locale_from_request(request) if request else settings.DEFAULT_LOCALE
            t = translations.get(current_locale, translations['en'])
        return t.gettext(text)
    return _inner

templates_dir = os.path.join(settings.PROJECT_ROOT, 'templates')
templates = Jinja2Templates(directory=templates_dir)

templates.env.globals['_'] = lambda text, request: gettext_lazy(text)(request)
templates.env.globals['get_locale_from_request'] = get_locale_from_request
templates.env.filters['currency_format'] = lambda value, locale='en': f"${value:,.2f}" if locale == 'en' else f"{value:,.2f} {str(gettext_lazy('currency')(Request()))}"

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def is_owner_available(db: Session, owner_id: int, service_id: int, start_time: datetime, end_time: datetime) -> bool:
    day_of_week = start_time.weekday()
    
    owner_availability_slots = db.query(models.Availability).filter(
        models.Availability.owner_id == owner_id,
        models.Availability.day_of_week == day_of_week
    ).all()

    if not owner_availability_slots:
        return False

    is_within_availability = False
    for slot in owner_availability_slots:
        avail_start_time_obj = datetime.strptime(slot.start_time, "%H:%M").time()
        avail_end_time_obj = datetime.strptime(slot.end_time, "%H:%M").time()

        if start_time.time() >= avail_start_time_obj and end_time.time() <= avail_end_time_obj:
            is_within_availability = True
            break
    
    if not is_within_availability:
        return False

    overlapping_bookings = db.query(models.Booking).filter(
        models.Booking.owner_id == owner_id,
        models.Booking.status != "cancelled",
        models.Booking.start_time < end_time,
        models.Booking.end_time > start_time
    ).count()

    if overlapping_bookings > 0:
        return False

    return True

@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.post("/token", response_model=schemas.Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    owner = db.query(models.Owner).filter(models.Owner.email == form_data.username).first()
    if not owner or not security.verify_password(form_data.password, owner.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(gettext_lazy("Incorrect email or password")(Request())),
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": owner.email}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/owners/", response_model=schemas.Owner)
async def create_owner(owner: schemas.OwnerCreate, db: Session = Depends(get_db)):
    db_owner = db.query(models.Owner).filter(models.Owner.email == owner.email).first()
    if db_owner:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(gettext_lazy("Email already registered")(Request())))
    hashed_password = security.get_password_hash(owner.password)
    db_owner = models.Owner(
        email=owner.email,
        hashed_password=hashed_password,
        business_name=owner.business_name,
        phone_number=owner.phone_number,
        default_locale=owner.default_locale
    )
    db.add(db_owner)
    db.commit()
    db.refresh(db_owner)
    return db_owner

@app.get("/owners/me/", response_model=schemas.Owner)
async def read_owners_me(current_owner: models.Owner = Depends(security.get_current_active_owner)):
    return current_owner

@app.put("/owners/me/", response_model=schemas.Owner)
async def update_owner_profile(
    owner_update: schemas.OwnerBase,
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(security.get_current_active_owner)
):
    try:
        current_owner.business_name = owner_update.business_name
        current_owner.phone_number = owner_update.phone_number
        current_owner.default_locale = owner_update.default_locale
        db.commit()
        db.refresh(current_owner)
        return current_owner
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(gettext_lazy(f"Failed to update profile: {e}")(Request())))


@app.post("/services/", response_model=schemas.Service)
async def create_service_for_owner(
    service: schemas.ServiceCreate,
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(security.get_current_active_owner)
):
    db_service = models.Service(**service.dict(), owner_id=current_owner.id)
    db.add(db_service)
    db.commit()
    db.refresh(db_service)
    return db_service

@app.get("/services/", response_model=List[schemas.Service])
async def read_owner_services(
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(security.get_current_active_owner)
):
    services = db.query(models.Service).filter(models.Service.owner_id == current_owner.id).all()
    return services

@app.get("/booking-page/{owner_id}", response_class=HTMLResponse)
async def get_public_booking_page(owner_id: int, request: Request, db: Session = Depends(get_db)):
    owner = db.query(models.Owner).filter(models.Owner.id == owner_id).first()
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(gettext_lazy("Owner not found")(request)))
    
    services = db.query(models.Service).filter(models.Service.owner_id == owner_id, models.Service.is_active == True).all()
    
    locale = get_locale_from_request(request)

    return templates.TemplateResponse(
        "booking_page.html",
        {"request": request, "owner": owner, "services": services, "locale": locale, "_": gettext_lazy, "settings": settings}
    )

@app.post("/bookings/", response_model=schemas.Booking, status_code=status.HTTP_201_CREATED)
async def create_booking(
    booking: schemas.BookingCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    service = db.query(models.Service).filter(models.Service.id == booking.service_id).first()
    if not service:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(gettext_lazy("Service not found")(Request())))
    
    owner = db.query(models.Owner).filter(models.Owner.id == service.owner_id).first()
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(gettext_lazy("Owner for service not found")(Request())))

    booking_end_time = booking.start_time + timedelta(minutes=service.duration_minutes)

    if not is_owner_available(db, owner.id, service.id, booking.start_time, booking_end_time):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(gettext_lazy("The requested time slot is not available. Please choose another time.")(Request()))
        )

    db_booking = models.Booking(
        **booking.dict(),
        owner_id=owner.id,
        end_time=booking_end_time,
        status="confirmed"
    )
    db.add(db_booking)
    try:
        db.commit()
        db.refresh(db_booking)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(gettext_lazy(f"Failed to create booking: {e}")(Request())))

    background_tasks.add_task(
        notifications.send_booking_confirmation_emails,
        db_booking=db_booking,
        owner_email=owner.email,
        owner_name=owner.business_name,
        owner_locale=owner.default_locale
    )
    background_tasks.add_task(
        notifications.send_booking_confirmation_whatsapp,
        db_booking=db_booking,
        owner_phone=owner.phone_number,
        owner_name=owner.business_name,
        owner_locale=owner.default_locale
    )

    return db_booking

@app.post("/bookings/recurring", response_model=List[schemas.Booking], status_code=status.HTTP_201_CREATED)
async def create_recurring_booking(
    recurring_booking_data: schemas.RecurringBookingCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(security.get_current_owner)
):
    owner_id = current_owner.id

    service = db.query(models.Service).filter(
        models.Service.id == recurring_booking_data.service_id,
        models.Service.owner_id == owner_id
    ).first()

    if not service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(gettext_lazy("Service not found or does not belong to the current owner.")(Request()))
        )

    recurrence_group_id = str(uuid4())
    generated_bookings = []
    current_occurrence_start_time = recurring_booking_data.first_occurrence_start_time
    occurrence_count = 0

    while True:
        if recurring_booking_data.number_of_occurrences is not None and occurrence_count >= recurring_booking_data.number_of_occurrences:
            break
        if recurring_booking_data.recurrence_end_date is not None and current_occurrence_start_time.date() > recurring_booking_data.recurrence_end_date:
            break
        
        if occurrence_count >= 100:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(gettext_lazy("Too many occurrences requested. Please limit recurring bookings to 100 per request.")(Request()))
            )

        current_occurrence_end_time = current_occurrence_start_time + timedelta(minutes=recurring_booking_data.duration_minutes)

        if not is_owner_available(db, owner_id, service.id, current_occurrence_start_time, current_occurrence_end_time):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(gettext_lazy(f"Time slot {current_occurrence_start_time.strftime('%Y-%m-%d %H:%M')} is not available for an occurrence in the series.")(Request()))
            )

        db_booking = models.Booking(
            service_id=service.id,
            owner_id=owner_id,
            customer_name=recurring_booking_data.customer_name,
            customer_email=recurring_booking_data.customer_email,
            customer_phone=recurring_booking_data.customer_phone,
            start_time=current_occurrence_start_time,
            end_time=current_occurrence_end_time,
            status="confirmed",
            recurrence_group_id=recurrence_group_id
        )
        db.add(db_booking)
        generated_bookings.append(db_booking)

        occurrence_count += 1

        if recurring_booking_data.recurrence_type == "daily":
            current_occurrence_start_time += timedelta(days=recurring_booking_data.recurrence_interval)
        elif recurring_booking_data.recurrence_type == "weekly":
            current_occurrence_start_time += timedelta(weeks=recurring_booking_data.recurrence_interval)
        elif recurring_booking_data.recurrence_type == "monthly":
            next_month = current_occurrence_start_time.month + recurring_booking_data.recurrence_interval
            next_year = current_occurrence_start_time.year
            if next_month > 12:
                next_year += (next_month - 1) // 12
                next_month = (next_month - 1) % 12 + 1

            _, last_day = calendar.monthrange(next_year, next_month)
            target_day = min(current_occurrence_start_time.day, last_day)

            current_occurrence_start_time = current_occurrence_start_time.replace(
                year=next_year,
                month=next_month,
                day=target_day
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(gettext_lazy("Invalid recurrence type provided.")(Request()))
            )

    try:
        db.commit()
        for booking in generated_bookings:
            db.refresh(booking)
            background_tasks.add_task(
                notifications.send_booking_confirmation_emails,
                db_booking=booking,
                owner_email=current_owner.email,
                owner_name=current_owner.business_name,
                owner_locale=current_owner.default_locale
            )
            background_tasks.add_task(
                notifications.send_booking_confirmation_whatsapp,
                db_booking=booking,
                owner_phone=current_owner.phone_number,
                owner_name=current_owner.business_name,
                owner_locale=current_owner.default_locale
            )

        return generated_bookings
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(gettext_lazy(f"Failed to create recurring bookings: {e}")(Request()))
        )

@app.get("/dashboard", response_class=HTMLResponse)
async def owner_dashboard(request: Request, db: Session = Depends(get_db), current_owner: models.Owner = Depends(security.get_current_owner)):
    locale = get_locale_from_request(request)
    
    upcoming_bookings = db.query(models.Booking).filter(
        models.Booking.owner_id == current_owner.id,
        models.Booking.start_time >= datetime.utcnow(),
        models.Booking.status == "confirmed"
    ).order_by(models.Booking.start_time).all()

    monthly_counts = get_monthly_booking_counts(db, current_owner.id)
    popular_services = get_popular_services(db, current_owner.id)

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "owner": current_owner,
            "bookings": upcoming_bookings,
            "monthly_booking_counts": json.dumps(monthly_counts),
            "popular_services": json.dumps(popular_services),
            "locale": locale,
            "_": gettext_lazy,
            "settings": settings
        }
    )

@app.post("/create-checkout-session")
async def create_stripe_checkout_session(request: Request, current_owner: models.Owner = Depends(security.get_current_owner)):
    if current_owner.is_premium:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(gettext_lazy("Owner is already subscribed to premium.")(Request())))
    
    try:
        session_id = create_checkout_session(current_owner.email, current_owner.id)
        return {"session_id": session_id}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(gettext_lazy(f"Failed to create Stripe checkout session: {e}")(Request())))

@app.post("/stripe-webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get('stripe-signature')

    if not sig_header:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No Stripe-Signature header")

    try:
        event = handle_webhook_event(payload, sig_header)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        customer_email = session.get('customer_details', {}).get('email')
        owner_id = session.get('metadata', {}).get('owner_id')
        stripe_customer_id = session.get('customer')
        subscription_id = session.get('subscription')

        if owner_id and customer_email:
            owner = db.query(models.Owner).filter(models.Owner.id == owner_id).first()
            if owner:
                owner.is_premium = True
                owner.stripe_customer_id = stripe_customer_id
                owner.stripe_subscription_id = subscription_id
                db.commit()
                db.refresh(owner)
                print(f"Owner {owner.email} (ID: {owner.id}) upgraded to premium.")
            else:
                print(f"Owner with ID {owner_id} not found for premium upgrade.")
        else:
            print("Missing owner_id or customer_email in checkout.session.completed event.")
    elif event['type'] == 'customer.subscription.deleted':
        subscription = event['data']['object']
        stripe_subscription_id = subscription.get('id')
        owner = db.query(models.Owner).filter(models.Owner.stripe_subscription_id == stripe_subscription_id).first()
        if owner:
            owner.is_premium = False
            owner.stripe_subscription_id = None
            db.commit()
            db.refresh(owner)
            print(f"Owner {owner.email} (ID: {owner.id}) subscription cancelled.")
        else:
            print(f"Owner with subscription ID {stripe_subscription_id} not found for subscription cancellation.")
    else:
        print(f"Unhandled event type {event['type']}")

    return Response(status_code=status.HTTP_200_OK)

@app.get("/api/analytics/monthly-bookings")
async def get_monthly_bookings_api(
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(security.get_current_owner)
):
    monthly_counts = get_monthly_booking_counts(db, current_owner.id)
    return monthly_counts

@app.get("/api/analytics/popular-services")
async def get_popular_services_api(
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(security.get_current_owner)
):
    popular_services = get_popular_services(db, current_owner.id)
    return popular_services

@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    owners = db.query(models.Owner).all()
    locale = get_locale_from_request(request)
    return templates.TemplateResponse(
        "admin_dashboard.html",
        {"request": request, "owners": owners, "locale": locale, "_": gettext_lazy, "settings": settings}
    )

@app.get("/admin/owners", response_model=List[schemas.Owner])
async def list_owners(db: Session = Depends(get_db)):
    return db.query(models.Owner).all()

@app.get("/admin/owners/{owner_id}", response_model=schemas.Owner)
async def get_owner(owner_id: int, db: Session = Depends(get_db)):
    owner = db.query(models.Owner).filter(models.Owner.id == owner_id).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")
    return owner

@app.put("/admin/owners/{owner_id}", response_model=schemas.Owner)
async def update_owner(owner_id: int, owner_update: schemas.OwnerBase, db: Session = Depends(get_db)):
    owner = db.query(models.Owner).filter(models.Owner.id == owner_id).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")
    
    for key, value in owner_update.dict(exclude_unset=True).items():
        setattr(owner, key, value)
    db.commit()
    db.refresh(owner)
    return owner

@app.delete("/admin/owners/{owner_id}", status_code=204)
async def delete_owner(owner_id: int, db: Session = Depends(get_db)):
    owner = db.query(models.Owner).filter(models.Owner.id == owner_id).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")
    db.delete(owner)
    db.commit()
    return Response(status_code=204)
