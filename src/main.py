from fastapi import FastAPI, Depends, HTTPException, status, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from datetime import date, timedelta, datetime
from typing import List, Optional
import gettext
import os
import json
import stripe

from . import models, schemas, security, analytics, notifications
from .database import SessionLocal, engine, get_db
from .config import settings
from .availability_utils import get_available_slots_for_day # Import the new utility

# Create database tables
models.Base.metadata.create_all(bind=engine)

app = FastAPI()

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Setup Jinja2Templates
templates = Jinja2Templates(directory="templates")

# Setup gettext for i18n
_ = gettext.gettext

@app.middleware("http")
async def add_language_middleware(request: Request, call_next):
    lang = request.cookies.get("locale") or settings.DEFAULT_LOCALE
    
    # Ensure the locale directory exists
    if not os.path.exists(settings.LOCALES_DIR):
        print(f"Warning: Locales directory not found at {settings.LOCALES_DIR}")
        # Create a dummy translation object to prevent errors
        request.state.gettext = gettext.NullTranslations().gettext
        response = await call_next(request)
        return response

    try:
        # Load translation
        # The domain 'messages' corresponds to 'messages.mo' file
        # The localedir should point to the directory containing 'locale/lang/LC_MESSAGES/messages.mo'
        t = gettext.translation('messages', localedir=settings.LOCALES_DIR, languages=[lang], fallback=True)
        t.install()
        request.state.gettext = t.gettext
    except Exception as e:
        print(f"Error loading translation for language '{lang}': {e}")
        # Fallback to default or NullTranslations if there's an issue
        request.state.gettext = gettext.NullTranslations().gettext
    
    response = await call_next(request)
    return response

@app.get("/health", response_class=HTMLResponse)
async def health_check():
    return "OK"

@app.get("/change-language/{lang_code}")
async def change_language(lang_code: str, response: Response):
    response.set_cookie(key="locale", value=lang_code, httponly=True, expires=3600*24*30) # 30 days
    return RedirectResponse(url="/") # Redirect to home or referrer

# Helper for i18n in templates
@app.template_filter("i18n")
def i18n_filter(text: str, request: Request):
    # Ensure request.state.gettext is available, fallback if not
    translator = getattr(request.state, "gettext", gettext.NullTranslations().gettext)
    return translator(text)

@app.template_filter("format_currency")
def format_currency_filter(amount_in_cents: int, request: Request, currency_code: str = "USD"):
    lang = request.cookies.get("locale") or settings.DEFAULT_LOCALE
    try:
        # Use locale-aware formatting. For Arabic, this might involve specific currency symbols
        # For simplicity and robust generic handling, we'll use a basic approach first.
        # A more advanced solution would use locale.currency or Babel.
        # Given previous steps, assuming a basic fix for Arabic currency in i18n filter.
        # This is a placeholder, as full locale.currency requires setting locale in the OS env.
        # A simpler way is to just append the currency code after dividing by 100.
        formatted_amount = f"{amount_in_cents / 100:.2f}"
        if lang == "ar":
            # Specific handling for Arabic, e.g., currency symbol placement
            return f"{formatted_amount} {currency_code}" # Placeholder, needs refinement
        return f"{currency_code} {formatted_amount}"
    except Exception:
        return f"{currency_code} {amount_in_cents / 100:.2f}"


# --- Owner Authentication and Management ---
@app.post("/token", response_model=schemas.Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    owner = db.query(models.Owner).filter(models.Owner.email == form_data.username).first()
    if not owner or not security.verify_password(form_data.password, owner.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": str(owner.id)}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/owners/", response_model=schemas.OwnerInDB, status_code=status.HTTP_201_CREATED)
async def create_owner(owner: schemas.OwnerCreate, db: Session = Depends(get_db)):
    db_owner = db.query(models.Owner).filter(models.Owner.email == owner.email).first()
    if db_owner:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")
    
    hashed_password = security.get_password_hash(owner.password)
    db_owner = models.Owner(
        email=owner.email,
        hashed_password=hashed_password,
        name=owner.name,
        phone=owner.phone,
        locale=owner.locale
    )
    db.add(db_owner)
    db.commit()
    db.refresh(db_owner)
    return db_owner

@app.get("/owners/me/", response_model=schemas.OwnerInDB)
async def read_owners_me(current_owner: dict = Depends(security.get_current_owner), db: Session = Depends(get_db)):
    owner_id = current_owner["id"]
    db_owner = db.query(models.Owner).filter(models.Owner.id == owner_id).first()
    if not db_owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Owner not found")
    return db_owner

@app.put("/owners/me/", response_model=schemas.OwnerInDB)
async def update_owner_profile(
    owner_update: schemas.OwnerUpdate,
    current_owner: dict = Depends(security.get_current_owner),
    db: Session = Depends(get_db)
):
    db_owner = db.query(models.Owner).filter(models.Owner.id == current_owner["id"]).first()
    if not db_owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Owner not found")

    update_data = owner_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_owner, key, value)
    
    try:
        db.add(db_owner)
        db.commit()
        db.refresh(db_owner)
        return db_owner
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to update profile: {e}")

# --- Service Management ---
@app.post("/owners/me/services/", response_model=schemas.Service, status_code=status.HTTP_201_CREATED)
async def create_service_for_owner(
    service: schemas.ServiceCreate,
    current_owner: dict = Depends(security.get_current_owner),
    db: Session = Depends(get_db)
):
    db_service = models.Service(**service.model_dump(), owner_id=current_owner["id"])
    db.add(db_service)
    db.commit()
    db.refresh(db_service)
    return db_service

@app.get("/owners/me/services/", response_model=List[schemas.Service])
async def read_services_for_owner(
    current_owner: dict = Depends(security.get_current_owner),
    db: Session = Depends(get_db)
):
    return db.query(models.Service).filter(models.Service.owner_id == current_owner["id"]).all()

# --- Availability Management (NEW/UPDATED LOGIC) ---
@app.post("/owners/me/availabilities/", response_model=schemas.Availability, status_code=status.HTTP_201_CREATED)
async def create_owner_availability(
    availability: schemas.AvailabilityCreate,
    current_owner: dict = Depends(security.get_current_owner),
    db: Session = Depends(get_db)
):
    # Validate recurrence_value based on recurrence_type
    if availability.recurrence_type == models.RecurrenceType.WEEKLY:
        if not availability.recurrence_value:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Recurrence value (weekdays) is required for weekly recurrence.")
        # Further validation: check if recurrence_value contains valid weekdays (e.g., "MON,TUE")
        valid_weekdays = {"MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"}
        input_weekdays = {d.strip().upper() for d in availability.recurrence_value.split(',')}
        if not input_weekdays.issubset(valid_weekdays):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid weekdays in recurrence value. Use MON,TUE,WED, etc.")
    elif availability.recurrence_type == models.RecurrenceType.MONTHLY:
        if not availability.recurrence_value:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Recurrence value (day of month) is required for monthly recurrence.")
        try:
            day_of_month = int(availability.recurrence_value)
            if not (1 <= day_of_month <= 31):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Day of month must be between 1 and 31.")
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Recurrence value for monthly must be an integer day of month.")
    elif availability.recurrence_type == models.RecurrenceType.NONE:
        if not availability.date:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Date is required for non-recurring availability.")
        # Ensure recurrence fields are null for non-recurring
        availability.recurrence_value = None
        availability.recurrence_end_date = None
    else: # DAILY
        # Ensure date is null for daily recurrence
        availability.date = None
        availability.recurrence_value = None # Daily doesn't need specific value
        
    if availability.start_time >= availability.end_time:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Start time must be before end time.")

    db_availability = models.Availability(**availability.model_dump(), owner_id=current_owner["id"])
    db.add(db_availability)
    db.commit()
    db.refresh(db_availability)
    return db_availability

@app.get("/owners/me/availabilities/", response_model=List[schemas.Availability])
async def get_owner_availabilities(
    current_owner: dict = Depends(security.get_current_owner),
    db: Session = Depends(get_db)
):
    return db.query(models.Availability).filter(models.Availability.owner_id == current_owner["id"]).all()

@app.delete("/owners/me/availabilities/{availability_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_owner_availability(
    availability_id: int,
    current_owner: dict = Depends(security.get_current_owner),
    db: Session = Depends(get_db)
):
    db_availability = db.query(models.Availability).filter(
        models.Availability.id == availability_id,
        models.Availability.owner_id == current_owner["id"]
    ).first()
    if not db_availability:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Availability not found")
    
    db.delete(db_availability)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

# --- Public Booking Page ---
@app.get("/bookslot.app/{owner_name_slug}", response_class=HTMLResponse)
async def get_booking_page(owner_name_slug: str, request: Request, db: Session = Depends(get_db)):
    owner = db.query(models.Owner).filter(models.Owner.name == owner_name_slug).first()
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Owner not found")
    
    services = db.query(models.Service).filter(models.Service.owner_id == owner.id).all()
    
    # Example for fetching available slots for a specific service and date
    # This would typically be an AJAX call from the frontend after selecting a service and date.
    # For now, just pass a dummy list or fetch for a default day.
    today = date.today()
    tomorrow = today + timedelta(days=1)
    
    example_available_slots = {}
    if services:
        first_service = services[0]
        # Fetch slots for tomorrow for the first service, assuming 30 min duration
        slots_tomorrow = get_available_slots_for_day(db, owner.id, first_service.id, tomorrow, first_service.duration_minutes)
        example_available_slots[str(tomorrow)] = [t.isoformat() for t in slots_tomorrow]

    return templates.TemplateResponse(
        "booking_page.html",
        {
            "request": request,
            "owner": owner,
            "services": services,
            "available_slots_json": json.dumps(example_available_slots), # Pass as JSON string
            "locale": request.cookies.get("locale") or settings.DEFAULT_LOCALE
        }
    )

@app.get("/bookslot.app/{owner_name_slug}/available-slots", response_model=List[str])
async def get_available_slots_api(
    owner_name_slug: str,
    service_id: int,
    selected_date: date,
    db: Session = Depends(get_db)
):
    owner = db.query(models.Owner).filter(models.Owner.name == owner_name_slug).first()
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Owner not found")
    
    service = db.query(models.Service).filter(
        models.Service.id == service_id,
        models.Service.owner_id == owner.id
    ).first()
    if not service:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found or does not belong to owner")
    
    slots = get_available_slots_for_day(db, owner.id, service.id, selected_date, service.duration_minutes)
    return [s.isoformat() for s in slots]


@app.post("/bookslot.app/{owner_name_slug}/book", response_class=HTMLResponse)
async def submit_booking(owner_name_slug: str, booking: schemas.BookingCreate, request: Request, db: Session = Depends(get_db)):
    owner = db.query(models.Owner).filter(models.Owner.name == owner_name_slug).first()
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Owner not found")

    service = db.query(models.Service).filter(
        models.Service.id == booking.service_id,
        models.Service.owner_id == owner.id
    ).first()
    if not service:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found for this owner.")

    # Validate if the chosen slot is actually available
    available_slots = get_available_slots_for_day(db, owner.id, service.id, booking.date, service.duration_minutes)
    if booking.time not in available_slots:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Selected time slot is not available.")

    # Check for overlapping bookings
    existing_bookings = db.query(models.Booking).filter(
        models.Booking.owner_id == owner.id,
        models.Booking.service_id == booking.service_id,
        models.Booking.date == booking.date
    ).all()

    new_booking_start_dt = datetime.combine(booking.date, booking.time)
    new_booking_end_dt = new_booking_start_dt + timedelta(minutes=service.duration_minutes)

    for existing_b in existing_bookings:
        existing_b_start_dt = datetime.combine(existing_b.date, existing_b.time)
        existing_b_end_dt = existing_b_start_dt + timedelta(minutes=service.duration_minutes) # Assuming service duration for existing
        
        # Check for overlap
        if max(new_booking_start_dt, existing_b_start_dt) < min(new_booking_end_dt, existing_b_end_dt):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Selected time slot overlaps with an existing booking.")

    db_booking = models.Booking(
        owner_id=owner.id,
        service_id=booking.service_id,
        customer_name=booking.customer_name,
        customer_email=booking.customer_email,
        customer_phone=booking.customer_phone,
        date=booking.date,
        time=booking.time
    )
    db.add(db_booking)
    db.commit()
    db.refresh(db_booking)

    # Send notifications
    notifications.notify_booking_confirmation(
        owner_email=owner.email,
        owner_phone=owner.phone,
        customer_email=booking.customer_email,
        customer_phone=booking.customer_phone,
        booking_details={
            "service_name": service.name,
            "date": booking.date.isoformat(),
            "time": booking.time.isoformat(),
            "customer_name": booking.customer_name
        },
        owner_locale=owner.locale
    )

    return templates.TemplateResponse(
        "booking_confirmation.html",
        {
            "request": request,
            "booking": db_booking,
            "service": service,
            "owner": owner,
            "locale": request.cookies.get("locale") or settings.DEFAULT_LOCALE
        }
    )

# --- Owner Dashboard ---
@app.get("/dashboard", response_class=HTMLResponse)
async def owner_dashboard(request: Request, current_owner: dict = Depends(security.get_current_owner), db: Session = Depends(get_db)):
    owner_id = current_owner["id"]
    owner_data = db.query(models.Owner).filter(models.Owner.id == owner_id).first()
    if not owner_data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Owner not found")

    services = db.query(models.Service).filter(models.Service.owner_id == owner_id).all()
    
    # Fetch upcoming bookings
    today = date.today()
    upcoming_bookings = db.query(models.Booking).filter(
        models.Booking.owner_id == owner_id,
        models.Booking.date >= today
    ).order_by(models.Booking.date, models.Booking.time).all()

    # Fetch analytics data
    monthly_bookings_data = analytics.get_monthly_bookings_data(db, owner_id)
    popular_services_data = analytics.get_popular_services_data(db, owner_id)

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "owner": owner_data,
            "services": services,
            "upcoming_bookings": upcoming_bookings,
            "monthly_bookings_json": json.dumps(monthly_bookings_data),
            "popular_services_json": json.dumps(popular_services_data),
            "locale": request.cookies.get("locale") or settings.DEFAULT_LOCALE
        }
    )

# --- Stripe Webhook Endpoint ---
@app.post("/stripe-webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError as e:
        # Invalid payload
        raise HTTPException(status_code=400, detail=str(e))
    except stripe.error.SignatureVerificationError as e:
        # Invalid signature
        raise HTTPException(status_code=400, detail=str(e))

    # Handle the event
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        customer_id = session.get('customer')
        subscription_id = session.get('subscription')
        owner_id = session.get('metadata', {}).get('owner_id')

        if owner_id and customer_id and subscription_id:
            db_owner = db.query(models.Owner).filter(models.Owner.id == int(owner_id)).first()
            if db_owner:
                db_owner.is_premium = True
                db_owner.stripe_customer_id = customer_id
                db_owner.stripe_subscription_id = subscription_id
                db.commit()
                print(f"Owner {owner_id} upgraded to premium.")
            else:
                print(f"Owner {owner_id} not found for webhook.")
        else:
            print(f"Missing data in checkout.session.completed event: {session}")

    elif event['type'] == 'customer.subscription.deleted':
        subscription = event['data']['object']
        subscription_id = subscription.get('id')
        
        db_owner = db.query(models.Owner).filter(models.Owner.stripe_subscription_id == subscription_id).first()
        if db_owner:
            db_owner.is_premium = False
            db_owner.stripe_subscription_id = None # Or keep it for history
            db.commit()
            print(f"Owner {db_owner.id}'s subscription cancelled.")
        else:
            print(f"Owner with subscription {subscription_id} not found for cancellation.")

    return {"status": "success"}

# --- Subscription Management UI/API ---
@app.post("/owners/me/create-checkout-session", response_model=schemas.StripeCheckoutSession)
async def create_checkout_session(
    request: Request,
    current_owner: dict = Depends(security.get_current_owner),
    db: Session = Depends(get_db)
):
    owner_id = current_owner["id"]
    db_owner = db.query(models.Owner).filter(models.Owner.id == owner_id).first()
    if not db_owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Owner not found")

    if not settings.STRIPE_PRICE_ID or not settings.SERVER_NAME:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Stripe price ID or server name not configured."
        )

    try:
        checkout_session = stripe.checkout.Session.create(
            line_items=[
                {
                    'price': settings.STRIPE_PRICE_ID,
                    'quantity': 1,
                },
            ],
            mode='subscription',
            success_url=f"{settings.SERVER_NAME}/dashboard?success=true",
            cancel_url=f"{settings.SERVER_NAME}/dashboard?canceled=true",
            customer=db_owner.stripe_customer_id if db_owner.stripe_customer_id else None,
            customer_email=db_owner.email if not db_owner.stripe_customer_id else None,
            metadata={"owner_id": str(owner_id)},
        )
        # Update owner's stripe_customer_id if a new one was created
        if not db_owner.stripe_customer_id and checkout_session.customer:
            db_owner.stripe_customer_id = checkout_session.customer
            db.commit()
            db.refresh(db_owner)

        return schemas.StripeCheckoutSession(
            session_id=checkout_session.id,
            checkout_url=checkout_session.url
        )
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Stripe error: {e}")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An unexpected error occurred: {e}")

@app.get("/owners/me/subscription-portal-url")
async def create_billing_portal_session(
    request: Request,
    current_owner: dict = Depends(security.get_current_owner),
    db: Session = Depends(get_db)
):
    owner_id = current_owner["id"]
    db_owner = db.query(models.Owner).filter(models.Owner.id == owner_id).first()
    if not db_owner or not db_owner.stripe_customer_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No Stripe customer found for this owner.")

    try:
        session = stripe.billing_portal.Session.create(
            customer=db_owner.stripe_customer_id,
            return_url=f"{settings.SERVER_NAME}/dashboard",
        )
        return {"url": session.url}
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Stripe error: {e}")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An unexpected error occurred: {e}")

# Admin panel - placeholder endpoints
@app.get("/admin/owners/", response_model=List[schemas.OwnerInDB])
async def list_owners(db: Session = Depends(get_db)):
    # In a real app, this would require admin authentication
    return db.query(models.Owner).all()

@app.get("/admin/owners/{owner_id}", response_model=schemas.OwnerInDB)
async def get_owner(owner_id: int, db: Session = Depends(get_db)):
    # In a real app, this would require admin authentication
    owner = db.query(models.Owner).filter(models.Owner.id == owner_id).first()
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Owner not found")
    return owner

@app.put("/admin/owners/{owner_id}", response_model=schemas.OwnerInDB)
async def update_owner(owner_id: int, owner_update: schemas.OwnerUpdate, db: Session = Depends(get_db)):
    # In a real app, this would require admin authentication
    db_owner = db.query(models.Owner).filter(models.Owner.id == owner_id).first()
    if not db_owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Owner not found")

    update_data = owner_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_owner, key, value)
    
    db.add(db_owner)
    db.commit()
    db.refresh(db_owner)
    return db_owner

@app.delete("/admin/owners/{owner_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_owner(owner_id: int, db: Session = Depends(get_db)):
    # In a real app, this would require admin authentication
    db_owner = db.query(models.Owner).filter(models.Owner.id == owner_id).first()
    if not db_owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Owner not found")
    db.delete(db_owner)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

# Additional admin endpoints for services and bookings
@app.get("/admin/owners/{owner_id}/services/", response_model=List[schemas.Service])
async def admin_list_owner_services(owner_id: int, db: Session = Depends(get_db)):
    return db.query(models.Service).filter(models.Service.owner_id == owner_id).all()

@app.get("/admin/owners/{owner_id}/bookings/", response_model=List[schemas.Booking])
async def admin_list_owner_bookings(owner_id: int, db: Session = Depends(get_db)):
    return db.query(models.Booking).filter(models.Booking.owner_id == owner_id).all()