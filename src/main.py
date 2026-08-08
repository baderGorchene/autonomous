from fastapi import FastAPI, Depends, HTTPException, status, Request, Response, Query
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from sqlalchemy import func, extract
from datetime import datetime, timedelta, date, time
from typing import List, Annotated, Optional
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from starlette.background import BackgroundTasks
from starlette.responses import JSONResponse
from gettext import gettext as _ # Import gettext for i18n
from babel.numbers import format_currency
import stripe
import os

from . import models, schemas, security, notifications
from .database import SessionLocal, engine
from .config import settings

from dateutil.rrule import rrulestr, rrule, DAILY, WEEKLY, MO, TU, WE, TH, FR, SA, SU

# Ensure tables are created
models.Base.metadata.create_all(bind=engine)

app = FastAPI()

# Add Session Middleware for language and other session data
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

# Templates setup
templates = Jinja2Templates(directory="src/templates")

# Stripe configuration
stripe.api_key = settings.STRIPE_SECRET_KEY

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Jinja2 Global Functions and Filters for i18n and currency
@app.middleware("http")
async def add_i18n_and_context_middleware(request: Request, call_next):
    # Set default locale or get from session/header
    request.state.locale = request.session.get("locale", settings.DEFAULT_LOCALE)
    
    # Make _ (gettext) available in templates
    templates.env.globals['gettext'] = _
    templates.env.globals['_'] = _
    templates.env.globals['current_locale'] = request.state.locale

    # Currency formatting filter for Jinja2
    def currency_filter(value, currency_code=None, locale=None):
        if value is None:
            return ""
        # Assume value is in cents, convert to main unit
        amount = value / 100
        # Use request.state.locale if locale is not explicitly provided
        effective_locale = locale if locale else request.state.locale
        effective_currency_code = currency_code if currency_code else "USD" # Default to USD
        return format_currency(amount, effective_currency_code, locale=effective_locale)

    templates.env.filters['currency'] = currency_filter

    response = await call_next(request)
    return response

@app.get("/health", status_code=status.HTTP_200_OK)
async def health_check():
    return {"status": "ok", "message": "Service is healthy"}

@app.post("/token", response_model=schemas.Token)
async def login_for_access_token(form_data: Annotated[OAuth2PasswordRequestForm, Depends()], db: Session = Depends(get_db)):
    owner = security.authenticate_owner(db, form_data.username, form_data.password)
    if not owner:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = security.create_access_token(
        data={"sub": owner.email}
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/owners/register", response_model=schemas.Owner, status_code=status.HTTP_201_CREATED)
def register_owner(owner: schemas.OwnerCreate, db: Session = Depends(get_db)):
    db_owner = db.query(models.Owner).filter(models.Owner.email == owner.email).first()
    if db_owner:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    hashed_password = security.get_password_hash(owner.password)
    db_owner = models.Owner(email=owner.email, hashed_password=hashed_password, name=owner.name, phone=owner.phone, whatsapp_number=owner.whatsapp_number, currency=owner.currency, locale=owner.locale)
    db.add(db_owner)
    db.commit()
    db.refresh(db_owner)

    # Create Stripe Customer
    try:
        stripe_customer = stripe.Customer.create(email=owner.email, name=owner.name)
        db_owner.stripe_customer_id = stripe_customer.id
        db.commit()
        db.refresh(db_owner)
    except stripe.error.StripeError as e:
        print(f"Stripe customer creation failed: {e}")
        # Log the error, but don't prevent owner registration for now

    return db_owner

@app.get("/owner/me", response_model=schemas.Owner)
def read_owner_me(current_owner: Annotated[schemas.Owner, Depends(security.get_current_owner)]):
    return current_owner

@app.put("/owner/me", response_model=schemas.Owner)
def update_owner_me(
    owner_update: schemas.OwnerUpdate,
    db: Session = Depends(get_db),
    current_owner: schemas.Owner = Depends(security.get_current_owner)
):
    # Prevent changing email to an already registered one
    if owner_update.email and owner_update.email != current_owner.email:
        existing_owner = db.query(models.Owner).filter(models.Owner.email == owner_update.email).first()
        if existing_owner:
            raise HTTPException(status_code=400, detail="Email already registered by another user.")

    for key, value in owner_update.model_dump(exclude_unset=True).items():
        if key == "password" and value:
            setattr(current_owner, "hashed_password", security.get_password_hash(value))
        elif key != "id": # Prevent updating id
            setattr(current_owner, key, value)

    db.commit()
    db.refresh(current_owner)
    return current_owner

@app.post("/owner/services", response_model=schemas.Service, status_code=status.HTTP_201_CREATED)
def create_service(
    service: schemas.ServiceCreate,
    db: Session = Depends(get_db),
    current_owner: schemas.Owner = Depends(security.get_current_owner)
):
    db_service = models.Service(**service.model_dump(), owner_id=current_owner.id)
    db.add(db_service)
    db.commit()
    db.refresh(db_service)
    return db_service

@app.get("/owner/services", response_model=List[schemas.Service])
def get_owner_services(
    db: Session = Depends(get_db),
    current_owner: schemas.Owner = Depends(security.get_current_owner)
):
    return db.query(models.Service).filter(models.Service.owner_id == current_owner.id).all()

@app.get("/owner/services/{service_id}", response_model=schemas.Service)
def get_owner_service(
    service_id: int,
    db: Session = Depends(get_db),
    current_owner: schemas.Owner = Depends(security.get_current_owner)
):
    db_service = db.query(models.Service).filter(
        models.Service.id == service_id,
        models.Service.owner_id == current_owner.id
    ).first()
    if db_service is None:
        raise HTTPException(status_code=404, detail="Service not found")
    return db_service

@app.put("/owner/services/{service_id}", response_model=schemas.Service)
def update_owner_service(
    service_id: int,
    service_update: schemas.ServiceUpdate,
    db: Session = Depends(get_db),
    current_owner: schemas.Owner = Depends(security.get_current_owner)
):
    db_service = db.query(models.Service).filter(
        models.Service.id == service_id,
        models.Service.owner_id == current_owner.id
    ).first()
    if db_service is None:
        raise HTTPException(status_code=404, detail="Service not found")
    
    for key, value in service_update.model_dump(exclude_unset=True).items():
        setattr(db_service, key, value)
    
    db.commit()
    db.refresh(db_service)
    return db_service

@app.delete("/owner/services/{service_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_owner_service(
    service_id: int,
    db: Session = Depends(get_db),
    current_owner: schemas.Owner = Depends(security.get_current_owner)
):
    db_service = db.query(models.Service).filter(
        models.Service.id == service_id,
        models.Service.owner_id == current_owner.id
    ).first()
    if db_service is None:
        raise HTTPException(status_code=404, detail="Service not found")
    
    db.delete(db_service)
    db.commit()
    return {"ok": True}

# Helper function to generate slots from recurring rules
def generate_slots(
    owner_id: int,
    start_date: date,
    end_date: date,
    db: Session
) -> List[datetime]:
    rules = db.query(models.RecurringAvailabilityRule).filter(
        models.RecurringAvailabilityRule.owner_id == owner_id,
        models.RecurringAvailabilityRule.is_active == True
    ).all()

    all_potential_slots = set() # Use a set to avoid duplicates

    for rule in rules:
        try:
            # The dtstart for rrulestr should be the first effective start of the rule
            rule_dtstart_datetime = datetime.combine(rule.rule_start_date, rule.start_time)
            
            # The rrule_string should only contain the RRULE part, not DTSTART.
            # rrulestr will use the provided dtstart if it's not in the string.
            r = rrulestr(rule.rrule_string, dtstart=rule_dtstart_datetime)

            # Define the period for which we want to generate slots, respecting query and rule bounds
            query_period_start = datetime.combine(start_date, time.min)
            query_period_end = datetime.combine(end_date, time.max) # Go till end of the day

            effective_period_start = max(query_period_start, rule_dtstart_datetime)
            effective_period_end = query_period_end
            if rule.rule_end_date:
                effective_period_end = min(query_period_end, datetime.combine(rule.rule_end_date, time.max)) # End of rule_end_date

            # Generate occurrences within the effective period
            # rrule.between includes the start and end if they are occurrences.
            # We want occurrences *on* or *after* effective_period_start and *on* or *before* effective_period_end.
            occurrences = list(r.between(
                after=effective_period_start - timedelta(microseconds=1), 
                before=effective_period_end + timedelta(microseconds=1), 
                inc=True
            ))
            
            # For each occurrence date, generate time slots
            for occ in occurrences:
                # The 'occ' here will be a datetime object based on `rule_dtstart` and `rrule_string`.
                # We need to adjust its time part to be `rule.start_time` and `rule.end_time`.
                # The `occ.date()` gives us the date part for which the rule applies.
                
                current_slot_start = datetime.combine(occ.date(), rule.start_time)
                current_slot_end = datetime.combine(occ.date(), rule.end_time)

                while current_slot_start + timedelta(minutes=rule.slot_duration) <= current_slot_end:
                    all_potential_slots.add(current_slot_start)
                    current_slot_start += timedelta(minutes=rule.slot_duration)

        except Exception as e:
            print(f"Error processing rrule_string '{rule.rrule_string}' for rule {rule.id}: {e}")
            continue

    # Filter out already booked slots
    existing_bookings = db.query(models.Booking).filter(
        models.Booking.owner_id == owner_id,
        models.Booking.booking_time >= datetime.combine(start_date, time.min),
        models.Booking.booking_time <= datetime.combine(end_date, time.max)
    ).all()
    
    booked_slots = {b.booking_time for b in existing_bookings}

    # Filter out booked slots
    available_slots = [slot for slot in all_potential_slots if slot not in booked_slots]
    
    return sorted(available_slots)

@app.get("/owner/available_slots", response_model=List[datetime])
def get_available_slots_for_owner(
    start_date: date = Query(..., description="Start date for slot generation (YYYY-MM-DD)"),
    end_date: date = Query(..., description="End date for slot generation (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    current_owner: schemas.Owner = Depends(security.get_current_owner),
):
    if start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date cannot be after end_date")
    
    return generate_slots(current_owner.id, start_date, end_date, db)

@app.get("/public/owners/{owner_id}/available_slots", response_model=List[datetime])
def get_public_available_slots(
    owner_id: int,
    start_date: date = Query(..., description="Start date for slot generation (YYYY-MM-DD)"),
    end_date: date = Query(..., description="End date for slot generation (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
):
    db_owner = db.query(models.Owner).filter(models.Owner.id == owner_id).first()
    if not db_owner:
        raise HTTPException(status_code=404, detail="Owner not found")

    if start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date cannot be after end_date")
    
    # Ensure the date range isn't too large for public queries to prevent abuse
    if (end_date - start_date).days > 30: # Limit to 30 days
        raise HTTPException(status_code=400, detail="Date range for public slot query cannot exceed 30 days.")

    return generate_slots(owner_id, start_date, end_date, db)

@app.post("/owner/availability/recurring", response_model=schemas.RecurringAvailabilityRule)
def create_recurring_availability_rule(
    rule: schemas.RecurringAvailabilityRuleCreate,
    db: Session = Depends(get_db),
    current_owner: schemas.Owner = Depends(security.get_current_owner),
):
    db_rule = models.RecurringAvailabilityRule(**rule.model_dump(), owner_id=current_owner.id)
    db.add(db_rule)
    db.commit()
    db.refresh(db_rule)
    return db_rule

@app.get("/owner/availability/recurring", response_model=List[schemas.RecurringAvailabilityRule])
def get_recurring_availability_rules(
    db: Session = Depends(get_db),
    current_owner: schemas.Owner = Depends(security.get_current_owner),
):
    return db.query(models.RecurringAvailabilityRule).filter(models.RecurringAvailabilityRule.owner_id == current_owner.id).all()

@app.get("/owner/availability/recurring/{rule_id}", response_model=schemas.RecurringAvailabilityRule)
def get_recurring_availability_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    current_owner: schemas.Owner = Depends(security.get_current_owner),
):
    db_rule = db.query(models.RecurringAvailabilityRule).filter(
        models.RecurringAvailabilityRule.id == rule_id,
        models.RecurringAvailabilityRule.owner_id == current_owner.id
    ).first()
    if db_rule is None:
        raise HTTPException(status_code=404, detail="Recurring availability rule not found")
    return db_rule

@app.put("/owner/availability/recurring/{rule_id}", response_model=schemas.RecurringAvailabilityRule)
def update_recurring_availability_rule(
    rule_id: int,
    rule: schemas.RecurringAvailabilityRuleUpdate,
    db: Session = Depends(get_db),
    current_owner: schemas.Owner = Depends(security.get_current_owner),
):
    db_rule = db.query(models.RecurringAvailabilityRule).filter(
        models.RecurringAvailabilityRule.id == rule_id,
        models.RecurringAvailabilityRule.owner_id == current_owner.id
    ).first()
    if db_rule is None:
        raise HTTPException(status_code=404, detail="Recurring availability rule not found")

    for key, value in rule.model_dump(exclude_unset=True).items():
        setattr(db_rule, key, value)
    db.commit()
    db.refresh(db_rule)
    return db_rule

@app.delete("/owner/availability/recurring/{rule_id}", status_code=204)
def delete_recurring_availability_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    current_owner: schemas.Owner = Depends(security.get_current_owner),
):
    db_rule = db.query(models.RecurringAvailabilityRule).filter(
        models.RecurringAvailabilityRule.id == rule_id,
        models.RecurringAvailabilityRule.owner_id == current_owner.id
    ).first()
    if db_rule is None:
        raise HTTPException(status_code=404, detail="Recurring availability rule not found")
    db.delete(db_rule)
    db.commit()
    return {"ok": True}


@app.post("/bookings", response_model=schemas.Booking)
def create_booking(
    booking: schemas.BookingCreate,
    db: Session = Depends(get_db),
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    db_owner = db.query(models.Owner).filter(models.Owner.id == booking.owner_id).first()
    if not db_owner:
        raise HTTPException(status_code=404, detail="Owner not found")

    # Validate if the requested booking_time is a valid, available slot
    # Generate slots for the day of the booking
    booking_date = booking.booking_time.date()
    available_slots_for_day = generate_slots(booking.owner_id, booking_date, booking_date, db)

    if booking.booking_time not in available_slots_for_day:
        raise HTTPException(status_code=400, detail="Requested booking time is not available or already booked.")
    
    # Check if a booking already exists for this exact time - generate_slots already filters this, but good for explicit check
    existing_booking = db.query(models.Booking).filter(
        models.Booking.owner_id == booking.owner_id,
        models.Booking.booking_time == booking.booking_time
    ).first()
    if existing_booking:
        raise HTTPException(status_code=409, detail="This slot is already booked.")

    db_booking = models.Booking(**booking.model_dump())
    db.add(db_booking)
    db.commit()
    db.refresh(db_booking)

    background_tasks.add_task(notifications.send_booking_confirmation_email, db_booking, db_owner)
    if db_owner.whatsapp_number:
        background_tasks.add_task(notifications.send_booking_confirmation_whatsapp, db_booking, db_owner)
        
    return db_booking

@app.get("/bookings/{booking_id}", response_model=schemas.Booking)
def get_booking(booking_id: int, db: Session = Depends(get_db)):
    db_booking = db.query(models.Booking).filter(models.Booking.id == booking_id).first()
    if db_booking is None:
        raise HTTPException(status_code=404, detail="Booking not found")
    return db_booking

@app.get("/owner/bookings", response_model=List[schemas.Booking])
def get_owner_bookings(
    db: Session = Depends(get_db),
    current_owner: schemas.Owner = Depends(security.get_current_owner)
):
    return db.query(models.Booking).filter(models.Booking.owner_id == current_owner.id).order_by(models.Booking.booking_time).all()

@app.put("/owner/bookings/{booking_id}", response_model=schemas.Booking)
def update_owner_booking(
    booking_id: int,
    booking_update: schemas.BookingUpdate,
    db: Session = Depends(get_db),
    current_owner: schemas.Owner = Depends(security.get_current_owner)
):
    db_booking = db.query(models.Booking).filter(
        models.Booking.id == booking_id,
        models.Booking.owner_id == current_owner.id
    ).first()
    if db_booking is None:
        raise HTTPException(status_code=404, detail="Booking not found")

    for key, value in booking_update.model_dump(exclude_unset=True).items():
        setattr(db_booking, key, value)
    
    db.commit()
    db.refresh(db_booking)
    return db_booking

@app.get("/{owner_name}", response_class=HTMLResponse)
async def booking_page(request: Request, owner_name: str, db: Session = Depends(get_db)):
    owner = db.query(models.Owner).filter(func.lower(models.Owner.name) == func.lower(owner_name)).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")
    return templates.TemplateResponse("booking_page.html", {"request": request, "owner": owner, "_" : request.state.gettext, "current_locale": request.state.locale})

@app.get("/booking_confirmation", response_class=HTMLResponse)
async def booking_confirmation(request: Request, booking_id: int, db: Session = Depends(get_db)):
    booking = db.query(models.Booking).filter(models.Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    owner = db.query(models.Owner).filter(models.Owner.id == booking.owner_id).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found for booking")
    return templates.TemplateResponse("booking_confirmation.html", {"request": request, "booking": booking, "owner": owner, "_" : request.state.gettext, "current_locale": request.state.locale})

@app.get("/owner/dashboard", response_class=HTMLResponse)
async def owner_dashboard(request: Request, db: Session = Depends(get_db), current_owner: schemas.Owner = Depends(security.get_current_owner)):
    # Fetch analytics data
    today = date.today()
    start_of_month = today.replace(day=1)
    end_of_month = (start_of_month + timedelta(days=32)).replace(day=1) - timedelta(days=1)

    monthly_bookings_count = db.query(models.Booking).filter(
        models.Booking.owner_id == current_owner.id,
        models.Booking.booking_time >= start_of_month,
        models.Booking.booking_time <= end_of_month
    ).count()

    # Popular services (top 3 for the month)
    popular_services_data = db.query(
        models.Booking.service_name,
        func.count(models.Booking.id).label('service_count')
    ).filter(
        models.Booking.owner_id == current_owner.id,
        models.Booking.booking_time >= start_of_month,
        models.Booking.booking_time <= end_of_month
    ).group_by(models.Booking.service_name)
    .order_by(func.count(models.Booking.id).desc())
    .limit(3).all()
    
    popular_services = []
    for service_name, service_count in popular_services_data:
        popular_services.append({"name": service_name, "count": service_count})

    return templates.TemplateResponse("dashboard.html", {
        "request": request, 
        "owner": current_owner,
        "_" : request.state.gettext,
        "current_locale": request.state.locale,
        "monthly_bookings_count": monthly_bookings_count,
        "popular_services": popular_services
    })

@app.get("/owner/analytics/monthly_summary", response_model=dict)
async def get_monthly_summary(
    db: Session = Depends(get_db),
    current_owner: schemas.Owner = Depends(security.get_current_owner)
):
    today = date.today()
    start_of_month = today.replace(day=1)
    end_of_month = (start_of_month + timedelta(days=32)).replace(day=1) - timedelta(days=1)

    monthly_bookings_count = db.query(models.Booking).filter(
        models.Booking.owner_id == current_owner.id,
        models.Booking.booking_time >= start_of_month,
        models.Booking.booking_time <= end_of_month
    ).count()

    total_revenue_cents = db.query(func.sum(models.Booking.service_price)).filter(
        models.Booking.owner_id == current_owner.id,
        models.Booking.booking_time >= start_of_month,
        models.Booking.booking_time <= end_of_month
    ).scalar() or 0

    return {
        "monthly_bookings_count": monthly_bookings_count,
        "total_revenue_cents": total_revenue_cents,
    }


@app.get("/owner/analytics/popular_services", response_model=List[dict])
async def get_popular_services(
    db: Session = Depends(get_db),
    current_owner: schemas.Owner = Depends(security.get_current_owner)
):
    today = date.today()
    start_of_month = today.replace(day=1)
    end_of_month = (start_of_month + timedelta(days=32)).replace(day=1) - timedelta(days=1)

    popular_services_data = db.query(
        models.Booking.service_name,
        func.count(models.Booking.id).label('service_count')
    ).filter(
        models.Booking.owner_id == current_owner.id,
        models.Booking.booking_time >= start_of_month,
        models.Booking.booking_time <= end_of_month
    ).group_by(models.Booking.service_name)
    .order_by(func.count(models.Booking.id).desc())
    .limit(3).all()
    
    popular_services = []
    for service_name, service_count in popular_services_data:
        popular_services.append({"name": service_name, "count": service_count})
    
    return popular_services


@app.post("/create-checkout-session")
async def create_checkout_session(request: Request, current_owner: schemas.Owner = Depends(security.get_current_owner)):
    if not current_owner.stripe_customer_id:
        raise HTTPException(status_code=400, detail="Stripe customer ID not found for this owner.")
    
    try:
        checkout_session = stripe.checkout.Session.create(
            customer=current_owner.stripe_customer_id,
            line_items=[
                {
                    'price': settings.STRIPE_PRICE_ID,
                    'quantity': 1,
                },
            ],
            mode='subscription',
            success_url=f"{settings.SERVER_NAME}/owner/dashboard?session_id={{CHECKOUT_SESSION_ID}}&status=success",
            cancel_url=f"{settings.SERVER_NAME}/owner/dashboard?status=cancel",
        )
        return RedirectResponse(checkout_session.url, status_code=303)
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))

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
        raise HTTPException(status_code=400, detail=str(e))
    except stripe.error.SignatureVerificationError as e:
        # Invalid signature
        raise HTTPException(status_code=400, detail=str(e))

    # Handle the event
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        customer_id = session.get('customer')
        subscription_id = session.get('subscription')

        if customer_id and subscription_id:
            owner = db.query(models.Owner).filter(models.Owner.stripe_customer_id == customer_id).first()
            if owner:
                owner.subscription_status = "premium"
                # You might want to store the subscription_id on the owner model too
                db.commit()
                print(f"Owner {owner.id} subscribed to premium plan.")
            else:
                print(f"Owner not found for Stripe customer ID: {customer_id}")

    elif event['type'] == 'customer.subscription.deleted':
        subscription = event['data']['object']
        customer_id = subscription.get('customer')

        if customer_id:
            owner = db.query(models.Owner).filter(models.Owner.stripe_customer_id == customer_id).first()
            if owner:
                owner.subscription_status = "free"
                db.commit()
                print(f"Owner {owner.id}'s subscription canceled.")
            else:
                print(f"Owner not found for Stripe customer ID: {customer_id}")

    # ... handle other event types

    return JSONResponse(status_code=200, content={'status': 'success'})

@app.post("/manage-subscription")
async def manage_subscription(request: Request, current_owner: schemas.Owner = Depends(security.get_current_owner)):
    if not current_owner.stripe_customer_id:
        raise HTTPException(status_code=400, detail="Stripe customer ID not found for this owner.")

    try:
        # Get the customer's current subscriptions
        subscriptions = stripe.Subscription.list(customer=current_owner.stripe_customer_id, status='active', limit=1)
        
        if subscriptions.data:
            # If there's an active subscription, create a customer portal session
            session = stripe.billing_portal.Session.create(
                customer=current_owner.stripe_customer_id,
                return_url=f"{settings.SERVER_NAME}/owner/dashboard",
            )
            return RedirectResponse(session.url, status_code=303)
        else:
            # If no active subscription, redirect to checkout to subscribe
            return RedirectResponse(url="/create-checkout-session", status_code=303)
            
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/set_locale")
async def set_locale(request: Request, locale: str = Query(..., min_length=2, max_length=5)):
    request.session["locale"] = locale
    # Redirect back to the page the user came from
    return RedirectResponse(url=request.headers.get("referer", "/"), status_code=302)


# Admin Panel Routes (Basic CRUD for Owners)
@app.get("/admin/owners", response_model=List[schemas.Owner])
def get_all_owners(db: Session = Depends(get_db)):
    # In a real app, this would require admin authentication
    return db.query(models.Owner).all()

@app.get("/admin/owners/{owner_id}", response_model=schemas.Owner)
def get_owner_by_id(owner_id: int, db: Session = Depends(get_db)):
    # In a real app, this would require admin authentication
    owner = db.query(models.Owner).filter(models.Owner.id == owner_id).first()
    if not owner: 
        raise HTTPException(status_code=404, detail="Owner not found")
    return owner

@app.put("/admin/owners/{owner_id}", response_model=schemas.Owner)
def update_owner(owner_id: int, owner_update: schemas.OwnerUpdate, db: Session = Depends(get_db)):
    # In a real app, this would require admin authentication
    db_owner = db.query(models.Owner).filter(models.Owner.id == owner_id).first()
    if not db_owner:
        raise HTTPException(status_code=404, detail="Owner not found")
    
    # Prevent changing email to an already registered one by another owner
    if owner_update.email and owner_update.email != db_owner.email:
        existing_owner = db.query(models.Owner).filter(models.Owner.email == owner_update.email).first()
        if existing_owner and existing_owner.id != owner_id:
            raise HTTPException(status_code=400, detail="Email already registered by another owner.")

    for key, value in owner_update.model_dump(exclude_unset=True).items():
        if key == "password" and value:
            setattr(db_owner, "hashed_password", security.get_password_hash(value))
        else:
            setattr(db_owner, key, value)
    
    db.commit()
    db.refresh(db_owner)
    return db_owner

@app.delete("/admin/owners/{owner_id}", status_code=204)
def delete_owner(owner_id: int, db: Session = Depends(get_db)):
    # In a real app, this would require admin authentication
    db_owner = db.query(models.Owner).filter(models.Owner.id == owner_id).first()
    if not db_owner:
        raise HTTPException(status_code=404, detail="Owner not found")
    db.delete(db_owner)
    db.commit()
    return {"ok": True}

# Admin Panel Routes for Services (CRUD per owner)
@app.get("/admin/owners/{owner_id}/services", response_model=List[schemas.Service])
def get_owner_services_admin(owner_id: int, db: Session = Depends(get_db)):
    # In a real app, this would require admin authentication
    return db.query(models.Service).filter(models.Service.owner_id == owner_id).all()

@app.post("/admin/owners/{owner_id}/services", response_model=schemas.Service, status_code=status.HTTP_201_CREATED)
def create_service_admin(
    owner_id: int,
    service: schemas.ServiceCreate,
    db: Session = Depends(get_db)
):
    # In a real app, this would require admin authentication
    db_owner = db.query(models.Owner).filter(models.Owner.id == owner_id).first()
    if not db_owner:
        raise HTTPException(status_code=404, detail="Owner not found")
    db_service = models.Service(**service.model_dump(), owner_id=owner_id)
    db.add(db_service)
    db.commit()
    db.refresh(db_service)
    return db_service

@app.put("/admin/owners/{owner_id}/services/{service_id}", response_model=schemas.Service)
def update_service_admin(
    owner_id: int,
    service_id: int,
    service_update: schemas.ServiceUpdate,
    db: Session = Depends(get_db)
):
    # In a real app, this would require admin authentication
    db_service = db.query(models.Service).filter(
        models.Service.id == service_id,
        models.Service.owner_id == owner_id
    ).first()
    if db_service is None:
        raise HTTPException(status_code=404, detail="Service not found for this owner")
    
    for key, value in service_update.model_dump(exclude_unset=True).items():
        setattr(db_service, key, value)
    
    db.commit()
    db.refresh(db_service)
    return db_service

@app.delete("/admin/owners/{owner_id}/services/{service_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_service_admin(
    owner_id: int,
    service_id: int,
    db: Session = Depends(get_db)
):
    # In a real app, this would require admin authentication
    db_service = db.query(models.Service).filter(
        models.Service.id == service_id,
        models.Service.owner_id == owner_id
    ).first()
    if db_service is None:
        raise HTTPException(status_code=404, detail="Service not found for this owner")
    
    db.delete(db_service)
    db.commit()
    return {"ok": True}

# Admin Panel Routes for Bookings (CRUD per owner)
@app.get("/admin/owners/{owner_id}/bookings", response_model=List[schemas.Booking])
def get_owner_bookings_admin(owner_id: int, db: Session = Depends(get_db)):
    # In a real app, this would require admin authentication
    return db.query(models.Booking).filter(models.Booking.owner_id == owner_id).order_by(models.Booking.booking_time).all()

@app.put("/admin/owners/{owner_id}/bookings/{booking_id}", response_model=schemas.Booking)
def update_booking_admin(
    owner_id: int,
    booking_id: int,
    booking_update: schemas.BookingUpdate,
    db: Session = Depends(get_db)
):
    # In a real app, this would require admin authentication
    db_booking = db.query(models.Booking).filter(
        models.Booking.id == booking_id,
        models.Booking.owner_id == owner_id
    ).first()
    if db_booking is None:
        raise HTTPException(status_code=404, detail="Booking not found for this owner")

    for key, value in booking_update.model_dump(exclude_unset=True).items():
        setattr(db_booking, key, value)
    
    db.commit()
    db.refresh(db_booking)
    return db_booking

@app.delete("/admin/owners/{owner_id}/bookings/{booking_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_booking_admin(
    owner_id: int,
    booking_id: int,
    db: Session = Depends(get_db)
):
    # In a real app, this would require admin authentication
    db_booking = db.query(models.Booking).filter(
        models.Booking.id == booking_id,
        models.Booking.owner_id == owner_id
    ).first()
    if db_booking is None:
        raise HTTPException(status_code=404, detail="Booking not found for this owner")
    
    db.delete(db_booking)
    db.commit()
    return {"ok": True}
