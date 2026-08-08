from fastapi import FastAPI, Depends, HTTPException, status, Request, Response, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session, joinedload
from jose import JWTError, jwt
from datetime import timedelta, datetime, date, time
from typing import List, Optional
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from gettext import gettext as _ # For i18n in backend, though primarily used in templates
import pytz
import locale as pylocale
import calendar

from . import models, schemas, security, notifications
from .database import SessionLocal, engine
from .config import settings

import stripe
import json
import os

# Initialize database
models.Base.metadata.create_all(bind=engine)

app = FastAPI()

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Setup Jinja2Templates
templates = Jinja2Templates(directory="templates")

# Setup Stripe
stripe.api_key = settings.STRIPE_SECRET_KEY

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# OAuth2PasswordBearer for token authentication
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def get_current_owner(db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
        token_data = schemas.TokenData(email=email)
    except JWTError:
        raise credentials_exception
    owner = db.query(models.Owner).filter(models.Owner.email == token_data.email).first()
    if owner is None:
        raise credentials_exception
    return owner

def get_current_admin_user(db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
        token_data = schemas.TokenData(email=email)
    except JWTError:
        raise credentials_exception
    admin_user = db.query(models.AdminUser).filter(models.AdminUser.email == token_data.email).first()
    if admin_user is None:
        raise credentials_exception
    return admin_user

# Helper for i18n
@app.middleware("http")
async def add_i18n_context(request: Request, call_next):
    lang = request.cookies.get("lang", settings.DEFAULT_LOCALE)
    request.state.locale = lang
    try:
        # Set locale for number formatting
        if lang == "ar":
            pylocale.setlocale(pylocale.LC_ALL, 'ar_AE.utf8') # Example for Arabic in UAE
        elif lang == "fr":
            pylocale.setlocale(pylocale.LC_ALL, 'fr_FR.utf8') # Example for French in France
        else:
            pylocale.setlocale(pylocale.LC_ALL, 'en_US.utf8') # Default English
    except pylocale.Error:
        print(f"Warning: Locale {lang} not available. Using default C locale.")
        pylocale.setlocale(pylocale.LC_ALL, 'C')

    response = await call_next(request)
    return response

@app.get("/health")
async def health_check():
    return {"status": "ok", "message": "BookSlot is running!"}

@app.post("/token", response_model=schemas.Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
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

@app.post("/admin/token", response_model=schemas.Token)
async def admin_login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    admin_user = security.authenticate_admin_user(db, form_data.username, form_data.password)
    if not admin_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": admin_user.email, "is_admin": True}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/owner/register", response_model=schemas.OwnerInDB)
async def register_owner(owner: schemas.OwnerCreate, db: Session = Depends(get_db)):
    db_owner = db.query(models.Owner).filter(models.Owner.email == owner.email).first()
    if db_owner:
        raise HTTPException(status_code=400, detail="Email already registered")
    hashed_password = security.get_password_hash(owner.password)
    db_owner = models.Owner(email=owner.email, hashed_password=hashed_password, name=owner.name, phone=owner.phone, locale=owner.locale)
    db.add(db_owner)
    db.commit()
    db.refresh(db_owner)
    return db_owner

@app.get("/owner/me", response_model=schemas.OwnerInDB)
async def read_owners_me(current_owner: models.Owner = Depends(get_current_owner)):
    return current_owner

@app.patch("/owner/me", response_model=schemas.OwnerInDB)
async def update_owner_profile(owner_update: schemas.OwnerUpdate, db: Session = Depends(get_db), current_owner: models.Owner = Depends(get_current_owner)):
    for field, value in owner_update.model_dump(exclude_unset=True).items():
        setattr(current_owner, field, value)
    db.commit()
    db.refresh(current_owner)
    return current_owner

@app.post("/owner/services", response_model=schemas.Service)
async def create_service_for_owner(service: schemas.ServiceCreate, db: Session = Depends(get_db), current_owner: models.Owner = Depends(get_current_owner)):
    db_service = models.Service(**service.model_dump(), owner_id=current_owner.id)
    db.add(db_service)
    db.commit()
    db.refresh(db_service)
    return db_service

@app.get("/owner/services", response_model=List[schemas.Service])
async def read_owner_services(db: Session = Depends(get_db), current_owner: models.Owner = Depends(get_current_owner)):
    return current_owner.services

@app.get("/owner/services/{service_id}", response_model=schemas.Service)
async def read_owner_service(service_id: int, db: Session = Depends(get_db), current_owner: models.Owner = Depends(get_current_owner)):
    service = db.query(models.Service).filter(models.Service.id == service_id, models.Service.owner_id == current_owner.id).first()
    if service is None:
        raise HTTPException(status_code=404, detail="Service not found")
    return service

@app.patch("/owner/services/{service_id}", response_model=schemas.Service)
async def update_owner_service(service_id: int, service_update: schemas.ServiceUpdate, db: Session = Depends(get_db), current_owner: models.Owner = Depends(get_current_owner)):
    service = db.query(models.Service).filter(models.Service.id == service_id, models.Service.owner_id == current_owner.id).first()
    if service is None:
        raise HTTPException(status_code=404, detail="Service not found")
    for field, value in service_update.model_dump(exclude_unset=True).items():
        setattr(service, field, value)
    db.commit()
    db.refresh(service)
    return service

@app.delete("/owner/services/{service_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_owner_service(service_id: int, db: Session = Depends(get_db), current_owner: models.Owner = Depends(get_current_owner)):
    service = db.query(models.Service).filter(models.Service.id == service_id, models.Service.owner_id == current_owner.id).first()
    if service is None:
        raise HTTPException(status_code=404, detail="Service not found")
    db.delete(service)
    db.commit()
    return

# Recurring Availability Endpoints
@app.post("/owner/recurring-availabilities", response_model=schemas.RecurringAvailability)
async def create_recurring_availability(
    recurring_availability: schemas.RecurringAvailabilityCreate,
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(get_current_owner)
):
    if recurring_availability.service_id:
        service = db.query(models.Service).filter(
            models.Service.id == recurring_availability.service_id,
            models.Service.owner_id == current_owner.id
        ).first()
        if not service:
            raise HTTPException(status_code=404, detail="Service not found for this owner")

    db_recurring_availability = models.RecurringAvailability(
        **recurring_availability.model_dump(), owner_id=current_owner.id
    )
    db.add(db_recurring_availability)
    db.commit()
    db.refresh(db_recurring_availability)
    return db_recurring_availability

@app.get("/owner/recurring-availabilities", response_model=List[schemas.RecurringAvailability])
async def get_recurring_availabilities(
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(get_current_owner)
):
    return current_owner.recurring_availabilities

@app.get("/owner/recurring-availabilities/{recurring_id}", response_model=schemas.RecurringAvailability)
async def get_recurring_availability_by_id(
    recurring_id: int,
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(get_current_owner)
):
    recurring_availability = db.query(models.RecurringAvailability).filter(
        models.RecurringAvailability.id == recurring_id,
        models.RecurringAvailability.owner_id == current_owner.id
    ).first()
    if not recurring_availability:
        raise HTTPException(status_code=404, detail="Recurring availability not found")
    return recurring_availability

@app.patch("/owner/recurring-availabilities/{recurring_id}", response_model=schemas.RecurringAvailability)
async def update_recurring_availability(
    recurring_id: int,
    recurring_update: schemas.RecurringAvailabilityUpdate,
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(get_current_owner)
):
    recurring_availability = db.query(models.RecurringAvailability).filter(
        models.RecurringAvailability.id == recurring_id,
        models.RecurringAvailability.owner_id == current_owner.id
    ).first()
    if not recurring_availability:
        raise HTTPException(status_code=404, detail="Recurring availability not found")

    if recurring_update.service_id is not None and recurring_update.service_id != recurring_availability.service_id:
        service = db.query(models.Service).filter(
            models.Service.id == recurring_update.service_id,
            models.Service.owner_id == current_owner.id
        ).first()
        if not service:
            raise HTTPException(status_code=404, detail="Service not found for this owner")

    for field, value in recurring_update.model_dump(exclude_unset=True).items():
        setattr(recurring_availability, field, value)
    db.commit()
    db.refresh(recurring_availability)
    return recurring_availability

@app.delete("/owner/recurring-availabilities/{recurring_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_recurring_availability(
    recurring_id: int,
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(get_current_owner)
):
    recurring_availability = db.query(models.RecurringAvailability).filter(
        models.RecurringAvailability.id == recurring_id,
        models.RecurringAvailability.owner_id == current_owner.id
    ).first()
    if not recurring_availability:
        raise HTTPException(status_code=404, detail="Recurring availability not found")
    db.delete(recurring_availability)
    db.commit()
    return


# Helper function to generate bookable slots
def generate_bookable_slots(
    owner: models.Owner,
    service: models.Service,
    db: Session,
    target_date: date,
    timezone_str: str = "UTC"
) -> List[schemas.BookingTimeSlot]:
    # Use owner's locale for timezone if available, otherwise default to UTC
    # A more robust solution would allow owners to set their timezone explicitly
    try:
        tz = pytz.timezone(timezone_str)
    except pytz.UnknownTimeZoneError:
        tz = pytz.utc

    slots = []
    service_duration = service.duration_minutes
    day_of_week_int = target_date.weekday() # Monday is 0, Sunday is 6

    # Get recurring availabilities for the target_date and service (or general)
    recurring_availabilities = db.query(models.RecurringAvailability).filter(
        models.RecurringAvailability.owner_id == owner.id,
        models.RecurringAvailability.is_active == True,
        models.RecurringAvailability.day_of_week == day_of_week_int,
        (models.RecurringAvailability.service_id == service.id) | (models.RecurringAvailability.service_id == None),
        (models.RecurringAvailability.start_date == None) | (models.RecurringAvailability.start_date <= target_date),
        (models.RecurringAvailability.end_date == None) | (models.RecurringAvailability.end_date >= target_date)
    ).all()

    # Get specific date availabilities (overrides recurring) for the target_date
    specific_availabilities = db.query(models.Availability).filter(
        models.Availability.owner_id == owner.id,
        models.Availability.date == target_date,
        (models.Availability.service_id == service.id) | (models.Availability.service_id == None),
    ).all()

    # Combine and process availabilities
    # Priority: Specific Date Availability (explicit true/false) > Recurring Availability
    effective_time_slots = [] # List of (start_time, end_time, is_available) for the day

    # Process recurring availabilities first
    for ra in recurring_availabilities:
        effective_time_slots.append((ra.start_time, ra.end_time, ra.is_active))

    # Apply specific availabilities (override recurring ones for the same time range)
    # This logic can become complex for overlapping specific overrides. For MVP, we'll assume
    # specific availabilities fully define the availability for their time range.
    # A more advanced approach would merge/subtract time intervals.
    for sa in specific_availabilities:
        # For simplicity, if a specific availability exists, it overrides any recurring for that time range.
        # A more complex merge logic would be needed for partial overlaps.
        effective_time_slots.append((sa.start_time, sa.end_time, sa.is_available))

    # Sort and merge/process effective time slots
    # This is a simplified merge, a real system would need robust interval tree or similar.
    # For MVP, we'll just consider the union of available blocks and generate slots from them.
    # Any explicitly unavailable specific availability will need to punch holes in recurring.
    # This is a placeholder for a more robust scheduling algorithm.
    # For now, let's treat `is_available=False` as a blockout.
    final_available_blocks = []
    for start_t, end_t, is_active in effective_time_slots:
        if is_active:
            final_available_blocks.append((start_t, end_t))

    # Sort and merge overlapping available blocks for simplicity
    final_available_blocks.sort(key=lambda x: x[0])
    merged_blocks = []
    if final_available_blocks:
        current_start, current_end = final_available_blocks[0]
        for i in range(1, len(final_available_blocks)):
            next_start, next_end = final_available_blocks[i]
            if next_start <= current_end:
                current_end = max(current_end, next_end)
            else:
                merged_blocks.append((current_start, current_end))
                current_start, current_end = next_start, next_end
        merged_blocks.append((current_start, current_end))

    # Generate slots from merged_blocks
    for block_start_time, block_end_time in merged_blocks:
        current_slot_start = datetime.datetime.combine(target_date, block_start_time, tzinfo=tz)
        block_end_datetime = datetime.datetime.combine(target_date, block_end_time, tzinfo=tz)

        while (current_slot_start + timedelta(minutes=service_duration)) <= block_end_datetime:
            slot_end = current_slot_start + timedelta(minutes=service_duration)
            # Check for existing bookings
            booking_exists = db.query(models.Booking).filter(
                models.Booking.owner_id == owner.id,
                models.Booking.service_id == service.id,
                models.Booking.booking_time == current_slot_start
            ).first()

            slots.append(schemas.BookingTimeSlot(
                start_time=current_slot_start,
                end_time=slot_end,
                is_bookable=not booking_exists
            ))
            current_slot_start += timedelta(minutes=service_duration)
    
    # Filter out slots in the past
    now_in_tz = datetime.datetime.now(tz)
    slots = [s for s in slots if s.start_time > now_in_tz]

    return slots


@app.get("/book/{owner_name}", response_class=HTMLResponse)
async def booking_page(
    request: Request,
    owner_name: str,
    db: Session = Depends(get_db),
    lang: Optional[str] = None
):
    owner = db.query(models.Owner).filter(models.Owner.name == owner_name).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")

    services = db.query(models.Service).filter(models.Service.owner_id == owner.id).all()
    if not services:
        raise HTTPException(status_code=404, detail="No services found for this owner")

    # Set language from query param or cookie
    if lang:
        response = RedirectResponse(url=request.url.path, status_code=status.HTTP_302_FOUND)
        response.set_cookie(key="lang", value=lang, httponly=True, expires=timedelta(days=30))
        request.state.locale = lang
        return response

    return templates.TemplateResponse(
        "booking_page.html",
        {
            "request": request,
            "owner": owner,
            "services": services,
            "_": request.state.locale, # Pass the locale for gettext
            "locale": request.state.locale,
            "settings": settings
        }
    )

@app.get("/book/{owner_name}/availability", response_model=List[schemas.DailyAvailability])
async def get_owner_availability(
    owner_name: str,
    service_id: int,
    start_date: date,
    end_date: date,
    db: Session = Depends(get_db)
):
    owner = db.query(models.Owner).filter(models.Owner.name == owner_name).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")

    service = db.query(models.Service).filter(models.Service.id == service_id, models.Service.owner_id == owner.id).first()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found for this owner")

    all_daily_availabilities = []
    current_date = start_date
    while current_date <= end_date:
        slots = generate_bookable_slots(owner, service, db, current_date, owner.locale) # Pass owner.locale for timezone hint
        all_daily_availabilities.append(schemas.DailyAvailability(date=current_date, slots=slots))
        current_date += timedelta(days=1)
    return all_daily_availabilities

@app.post("/book/{owner_name}/submit", response_class=HTMLResponse)
async def submit_booking(
    request: Request,
    owner_name: str,
    booking_data: schemas.BookingCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    owner = db.query(models.Owner).filter(models.Owner.name == owner_name).first()
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Owner not found")

    service = db.query(models.Service).filter(models.Service.id == booking_data.service_id, models.Service.owner_id == owner.id).first()
    if not service:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found for this owner")

    # Validate booking time against generated slots (using the same logic)
    # This is crucial to prevent booking unavailable slots
    booking_date = booking_data.booking_time.date()
    possible_slots = generate_bookable_slots(owner, service, db, booking_date, owner.locale)
    
    is_slot_valid = False
    for slot in possible_slots:
        if slot.start_time == booking_data.booking_time and slot.is_bookable:
            is_slot_valid = True
            break

    if not is_slot_valid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Selected time slot is not available or already booked.")

    # Check for existing booking at the exact time for the same service
    existing_booking = db.query(models.Booking).filter(
        models.Booking.service_id == booking_data.service_id,
        models.Booking.booking_time == booking_data.booking_time
    ).first()

    if existing_booking:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This time slot is already booked. Please choose another.")

    # Create booking
    db_booking = models.Booking(
        owner_id=owner.id,
        service_id=service.id,
        customer_name=booking_data.customer_name,
        customer_email=booking_data.customer_email,
        customer_phone=booking_data.customer_phone,
        booking_time=booking_data.booking_time
    )
    db.add(db_booking)
    db.commit()
    db.refresh(db_booking)

    confirmation_data = schemas.BookingConfirmation(
        owner_name=owner.name,
        owner_email=owner.email,
        customer_name=booking_data.customer_name,
        customer_email=booking_data.customer_email,
        service_name=service.name,
        booking_time=booking_data.booking_time,
        owner_phone=owner.phone,
        customer_phone=booking_data.customer_phone,
        booking_link=f"{settings.SERVER_NAME}/owner/dashboard" # Link for owner to view booking
    )

    # Send notifications in background
    background_tasks.add_task(notifications.send_booking_confirmation_emails, confirmation_data, owner.locale)
    background_tasks.add_task(notifications.send_booking_confirmation_whatsapp, confirmation_data, owner.locale)

    return templates.TemplateResponse(
        "booking_confirmation.html",
        {
            "request": request,
            "booking": db_booking,
            "owner": owner,
            "service": service,
            "_": request.state.locale,
            "locale": request.state.locale
        }
    )

@app.get("/owner/dashboard", response_class=HTMLResponse)
async def owner_dashboard(request: Request, db: Session = Depends(get_db), current_owner: models.Owner = Depends(get_current_owner)):
    # Fetch services with their recurring availabilities
    services_with_recurring = db.query(models.Service)
                                .options(joinedload(models.Service.recurring_availabilities))
                                .filter(models.Service.owner_id == current_owner.id)
                                .all()
    
    # Fetch upcoming bookings
    upcoming_bookings = db.query(models.Booking).filter(
        models.Booking.owner_id == current_owner.id,
        models.Booking.booking_time >= datetime.datetime.utcnow()
    ).order_by(models.Booking.booking_time).limit(10).all()

    # Analytics: Total bookings and revenue this month
    start_of_month = datetime.datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end_of_month = (start_of_month + timedelta(days=32)).replace(day=1) - timedelta(microseconds=1)

    total_bookings_this_month = db.query(models.Booking).filter(
        models.Booking.owner_id == current_owner.id,
        models.Booking.booking_time >= start_of_month,
        models.Booking.booking_time <= end_of_month
    ).count()

    # Revenue calculation (simplified: sum of service prices for bookings this month)
    # In a real app, this might involve actual payment records linked to bookings.
    bookings_for_revenue = db.query(models.Booking, models.Service).join(models.Service).filter(
        models.Booking.owner_id == current_owner.id,
        models.Booking.booking_time >= start_of_month,
        models.Booking.booking_time <= end_of_month
    ).all()

    total_revenue_this_month = sum(service.price for booking, service in bookings_for_revenue)

    # Popular services (top 3 by booking count this month)
    popular_services_query = db.query(models.Service.name, models.Service.price, models.Service.duration_minutes, 
                                      func.count(models.Booking.id).label('booking_count')) \
                                .join(models.Booking) \
                                .filter(models.Booking.owner_id == current_owner.id, 
                                        models.Booking.booking_time >= start_of_month, 
                                        models.Booking.booking_time <= end_of_month) \
                                .group_by(models.Service.id, models.Service.name, models.Service.price, models.Service.duration_minutes) \
                                .order_by(func.count(models.Booking.id).desc()) \
                                .limit(3).all()
    popular_services = []
    for service_name, service_price, service_duration, booking_count in popular_services_query:
        popular_services.append({"name": service_name, "price": service_price, "duration_minutes": service_duration, "booking_count": booking_count})

    # Subscription status
    subscription_status = schemas.SubscriptionStatus(
        status=current_owner.subscription_status,
        current_period_end=current_owner.current_period_end,
        is_premium=current_owner.subscription_status == "active"
    )

    dashboard_data = schemas.OwnerDashboardData(
        owner=current_owner,
        services=[schemas.OwnerServiceWithAvailability.model_validate(s) for s in services_with_recurring],
        upcoming_bookings=[schemas.Booking.model_validate(b) for b in upcoming_bookings],
        total_bookings_this_month=total_bookings_this_month,
        total_revenue_this_month=total_revenue_this_month,
        popular_services=popular_services,
        subscription_status=subscription_status
    )

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "owner": current_owner,
            "dashboard_data": dashboard_data,
            "_": request.state.locale,
            "locale": request.state.locale,
            "settings": settings
        }
    )

# Stripe webhook endpoint
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
        owner_id = session.get('metadata', {}).get('owner_id')

        if owner_id and customer_id and subscription_id:
            owner = db.query(models.Owner).filter(models.Owner.id == int(owner_id)).first()
            if owner:
                owner.stripe_customer_id = customer_id
                owner.subscription_status = "active"
                # Fetch subscription details to get current_period_end
                try:
                    subscription = stripe.Subscription.retrieve(subscription_id)
                    owner.current_period_end = datetime.datetime.fromtimestamp(subscription.current_period_end, tz=pytz.utc)
                except stripe.error.StripeError as e:
                    print(f"Stripe error retrieving subscription {subscription_id}: {e}")
                    # Log error but proceed, subscription_status is already updated
                db.commit()
                db.refresh(owner)
                print(f"Owner {owner.id} subscribed. Customer: {customer_id}, Subscription: {subscription_id}")

    elif event['type'] == 'customer.subscription.updated' or event['type'] == 'customer.subscription.deleted':
        subscription = event['data']['object']
        customer_id = subscription.get('customer')
        status = subscription.get('status')
        current_period_end = subscription.get('current_period_end')

        owner = db.query(models.Owner).filter(models.Owner.stripe_customer_id == customer_id).first()
        if owner:
            owner.subscription_status = status
            if current_period_end:
                owner.current_period_end = datetime.datetime.fromtimestamp(current_period_end, tz=pytz.utc)
            db.commit()
            db.refresh(owner)
            print(f"Owner {owner.id} subscription status updated to {status}")

    return Response(status_code=200)

@app.post("/owner/create-checkout-session", response_model=schemas.StripeCheckoutSession)
async def create_checkout_session(request: Request, db: Session = Depends(get_db), current_owner: models.Owner = Depends(get_current_owner)):
    if not settings.STRIPE_PRODUCT_ID or not settings.STRIPE_PRICE_ID:
        raise HTTPException(status_code=500, detail="Stripe product or price ID not configured.")

    try:
        checkout_session = stripe.checkout.Session.create(
            line_items=[
                {
                    'price': settings.STRIPE_PRICE_ID,
                    'quantity': 1,
                },
            ],
            mode='subscription',
            success_url=f"{settings.SERVER_NAME}/owner/dashboard?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{settings.SERVER_NAME}/owner/dashboard?cancelled=true",
            customer=current_owner.stripe_customer_id, # Use existing customer if available
            customer_email=current_owner.email if not current_owner.stripe_customer_id else None, # Only set if new customer
            metadata={
                'owner_id': str(current_owner.id),
            },
            subscription_data={
                'metadata': {
                    'owner_id': str(current_owner.id),
                },
            },
        )
        return schemas.StripeCheckoutSession(session_url=checkout_session.url)
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/owner/create-customer-portal-session", response_model=schemas.StripeCheckoutSession)
async def create_customer_portal_session(request: Request, db: Session = Depends(get_db), current_owner: models.Owner = Depends(get_current_owner)):
    if not current_owner.stripe_customer_id:
        raise HTTPException(status_code=400, detail="Owner does not have a Stripe customer ID.")
    
    try:
        portalSession = stripe.billing_portal.Session.create(
            customer=current_owner.stripe_customer_id,
            return_url=f"{settings.SERVER_NAME}/owner/dashboard",
        )
        return schemas.StripeCheckoutSession(session_url=portalSession.url)
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=500, detail=str(e))

# Admin Dashboard Routes
from sqlalchemy import func

@app.get("/admin/dashboard", response_class=HTMLResponse)
async def admin_dashboard(request: Request, db: Session = Depends(get_db), admin_user: models.AdminUser = Depends(get_current_admin_user)):
    owners = db.query(models.Owner).all()
    return templates.TemplateResponse("admin_dashboard.html", {"request": request, "admin_user": admin_user, "owners": owners, "_": request.state.locale, "locale": request.state.locale})

@app.get("/admin/owners", response_model=List[schemas.OwnerInDB])
async def get_all_owners(db: Session = Depends(get_db), admin_user: models.AdminUser = Depends(get_current_admin_user)):
    owners = db.query(models.Owner).all()
    return owners

@app.get("/admin/owners/{owner_id}", response_model=schemas.OwnerInDB)
async def get_owner_by_id(owner_id: int, db: Session = Depends(get_db), admin_user: models.AdminUser = Depends(get_current_admin_user)):
    owner = db.query(models.Owner).filter(models.Owner.id == owner_id).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")
    return owner

@app.patch("/admin/owners/{owner_id}", response_model=schemas.OwnerInDB)
async def update_owner_by_admin(owner_id: int, owner_update: schemas.OwnerUpdate, db: Session = Depends(get_db), admin_user: models.AdminUser = Depends(get_current_admin_user)):
    owner = db.query(models.Owner).filter(models.Owner.id == owner_id).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")
    for field, value in owner_update.model_dump(exclude_unset=True).items():
        setattr(owner, field, value)
    db.commit()
    db.refresh(owner)
    return owner

@app.delete("/admin/owners/{owner_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_owner_by_admin(owner_id: int, db: Session = Depends(get_db), admin_user: models.AdminUser = Depends(get_current_admin_user)):
    owner = db.query(models.Owner).filter(models.Owner.id == owner_id).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")
    db.delete(owner)
    db.commit()
    return

@app.get("/admin/owners/{owner_id}/services", response_model=List[schemas.Service])
async def get_owner_services_admin(owner_id: int, db: Session = Depends(get_db), admin_user: models.AdminUser = Depends(get_current_admin_user)):
    services = db.query(models.Service).filter(models.Service.owner_id == owner_id).all()
    return services

@app.get("/admin/owners/{owner_id}/bookings", response_model=List[schemas.Booking])
async def get_owner_bookings_admin(owner_id: int, db: Session = Depends(get_db), admin_user: models.AdminUser = Depends(get_current_admin_user)):
    bookings = db.query(models.Booking).filter(models.Booking.owner_id == owner_id).all()
    return bookings

@app.post("/admin/services", response_model=schemas.Service)
async def create_service_admin(service: schemas.ServiceCreate, owner_id: int, db: Session = Depends(get_db), admin_user: models.AdminUser = Depends(get_current_admin_user)):
    owner = db.query(models.Owner).filter(models.Owner.id == owner_id).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")
    db_service = models.Service(**service.model_dump(), owner_id=owner_id)
    db.add(db_service)
    db.commit()
    db.refresh(db_service)
    return db_service

@app.patch("/admin/services/{service_id}", response_model=schemas.Service)
async def update_service_admin(service_id: int, service_update: schemas.ServiceUpdate, db: Session = Depends(get_db), admin_user: models.AdminUser = Depends(get_current_admin_user)):
    service = db.query(models.Service).filter(models.Service.id == service_id).first()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    for field, value in service_update.model_dump(exclude_unset=True).items():
        setattr(service, field, value)
    db.commit()
    db.refresh(service)
    return service

@app.delete("/admin/services/{service_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_service_admin(service_id: int, db: Session = Depends(get_db), admin_user: models.AdminUser = Depends(get_current_admin_user)):
    service = db.query(models.Service).filter(models.Service.id == service_id).first()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    db.delete(service)
    db.commit()
    return

@app.get("/admin/bookings", response_model=List[schemas.Booking])
async def get_all_bookings_admin(db: Session = Depends(get_db), admin_user: models.AdminUser = Depends(get_current_admin_user)):
    bookings = db.query(models.Booking).all()
    return bookings

@app.patch("/admin/bookings/{booking_id}", response_model=schemas.Booking)
async def update_booking_admin(booking_id: int, booking_update: schemas.BookingCreate, db: Session = Depends(get_db), admin_user: models.AdminUser = Depends(get_current_admin_user)):
    booking = db.query(models.Booking).filter(models.Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    for field, value in booking_update.model_dump(exclude_unset=True).items():
        setattr(booking, field, value)
    db.commit()
    db.refresh(booking)
    return booking

@app.delete("/admin/bookings/{booking_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_booking_admin(booking_id: int, db: Session = Depends(get_db), admin_user: models.AdminUser = Depends(get_current_admin_user)):
    booking = db.query(models.Booking).filter(models.Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    db.delete(booking)
    db.commit()
    return
