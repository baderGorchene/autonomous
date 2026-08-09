from fastapi import FastAPI, Depends, HTTPException, status, Request, Form, APIRouter
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import date, time, datetime, timedelta
from typing import List, Optional, Tuple
import calendar
import uuid

from . import models, schemas, security, notifications, i18n, analytics, availability_utils
from .database import SessionLocal, engine
from .config import settings
from .stripe_utils import create_checkout_session, handle_webhook
from .analytics import get_monthly_bookings_data, get_popular_services_data

models.Base.metadata.create_all(bind=engine)

app = FastAPI()
router = APIRouter()

templates = Jinja2Templates(directory="templates")

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Helper to get current owner from JWT token
def get_current_owner(db: Session = Depends(get_db), token: str = Depends(security.oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    return security.get_current_owner(db, token)

# Helper for recurring bookings (moved from previous steps)
def create_recurring_bookings(
    db: Session, 
    owner: models.Owner, 
    service: models.Service, 
    initial_booking_data: schemas.BookingCreate, 
    recurrence_type: str, 
    recurrence_value: str,
    original_booking_id: int
):
    booking_start_dt = datetime.combine(initial_booking_data.date, initial_booking_data.time)
    # For simplicity, let's generate for the next 3 months, or a reasonable period.
    # In a real app, this would be configurable or tied to availability end dates.
    end_generation_date = booking_start_dt.date() + timedelta(days=90)

    current_date = booking_start_dt.date()
    while current_date <= end_generation_date:
        is_applicable = False
        if recurrence_type == models.RecurrenceType.DAILY.value:
            is_applicable = True
        elif recurrence_type == models.RecurrenceType.WEEKLY.value:
            weekdays = [d.strip().upper() for d in recurrence_value.split(',')]
            target_weekday_name = calendar.day_abbr[current_date.weekday()].upper()
            if target_weekday_name in weekdays:
                is_applicable = True
        elif recurrence_type == models.RecurrenceType.MONTHLY.value:
            try:
                day_of_month = int(recurrence_value)
                if current_date.day == day_of_month:
                    is_applicable = True
            except ValueError:
                pass # Handle more complex monthly rules if needed

        if is_applicable and current_date != initial_booking_data.date: # Don't re-create the initial booking
            # Check availability for the new date before creating
            available_slots = availability_utils.get_available_slots_for_day(
                db, owner.id, service.id, current_date, service.duration_minutes
            )
            if initial_booking_data.time in available_slots:
                new_booking = models.Booking(
                    owner_id=owner.id,
                    service_id=service.id,
                    customer_id=initial_booking_data.customer_id,
                    date=current_date,
                    time=initial_booking_data.time,
                    customer_name=initial_booking_data.customer_name,
                    customer_email=initial_booking_data.customer_email,
                    customer_phone=initial_booking_data.customer_phone,
                    is_confirmed=True, # Auto-confirm recurring bookings
                    is_recurring=True,
                    recurrence_id=initial_booking_data.recurrence_id
                )
                db.add(new_booking)
        
        current_date += timedelta(days=1)
    
    db.commit()

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse("home.html", {"request": request})

@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.post("/token", response_model=schemas.Token)
async def login_for_access_token(db: Session = Depends(get_db), form_data: security.OAuth2PasswordRequestForm = Depends()):
    owner = security.authenticate_owner(db, form_data.username, form_data.password)
    if not owner:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": owner.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/signup", response_model=schemas.Owner)
async def owner_signup(owner: schemas.OwnerCreate, db: Session = Depends(get_db)):
    db_owner = db.query(models.Owner).filter(models.Owner.username == owner.username).first()
    if db_owner:
        raise HTTPException(status_code=400, detail="Username already registered")
    db_owner = db.query(models.Owner).filter(models.Owner.email == owner.email).first()
    if db_owner:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    hashed_password = security.get_password_hash(owner.password)
    db_owner = models.Owner(username=owner.username, email=owner.email, hashed_password=hashed_password, phone_number=owner.phone_number, currency=owner.currency, locale=owner.locale)
    db.add(db_owner)
    db.commit()
    db.refresh(db_owner)
    return db_owner

@app.get("/dashboard", response_class=HTMLResponse)
async def owner_dashboard(request: Request, db: Session = Depends(get_db), current_owner: schemas.Owner = Depends(get_current_owner)):
    _ = i18n.gettext_locale(current_owner.locale) # Set locale for this request

    # Fetch services for the owner
    services = db.query(models.Service).filter(models.Service.owner_id == current_owner.id).all()

    # Fetch upcoming bookings (eagerly load service and customer)
    upcoming_bookings = db.query(models.Booking).join(models.Service).outerjoin(models.Customer).filter(
        models.Booking.owner_id == current_owner.id,
        models.Booking.date >= date.today()
    ).order_by(models.Booking.date, models.Booking.time).all()

    # Fetch monthly bookings data for analytics chart
    monthly_bookings_data = get_monthly_bookings_data(db, current_owner.id)
    popular_services_data = get_popular_services_data(db, current_owner.id)

    return templates.TemplateResponse(
        "dashboard.html", 
        {
            "request": request, 
            "owner": current_owner, 
            "services": services, 
            "upcoming_bookings": upcoming_bookings,
            "monthly_bookings_json": monthly_bookings_data, # Pass as JSON for JS chart
            "popular_services_json": popular_services_data,
            "gettext": _
        }
    )

@app.post("/dashboard/update_profile", response_class=RedirectResponse)
async def update_owner_profile(
    request: Request,
    email: EmailStr = Form(...),
    phone_number: Optional[str] = Form(None),
    currency: str = Form(...),
    locale: str = Form(...),
    db: Session = Depends(get_db),
    current_owner: schemas.Owner = Depends(get_current_owner)
):
    _ = i18n.gettext_locale(current_owner.locale)
    try:
        # Check if new email conflicts with another owner
        if email != current_owner.email:
            existing_owner = db.query(models.Owner).filter(models.Owner.email == email).first()
            if existing_owner and existing_owner.id != current_owner.id:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_("Email already registered by another owner."))

        current_owner.email = email
        current_owner.phone_number = phone_number
        current_owner.currency = currency
        current_owner.locale = locale
        db.add(current_owner)
        db.commit()
        db.refresh(current_owner)
        return RedirectResponse(url="/dashboard?status=profile_updated", status_code=status.HTTP_303_SEE_OTHER)
    except HTTPException as e:
        # On error, redirect back with an error message
        return RedirectResponse(url=f"/dashboard?error={e.detail}", status_code=status.HTTP_303_SEE_OTHER)
    except Exception:
        return RedirectResponse(url=f"/dashboard?error={_('An unexpected error occurred.')}", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/dashboard/add_service", response_class=RedirectResponse)
async def add_service(
    request: Request,
    name: str = Form(...),
    description: Optional[str] = Form(None),
    duration_minutes: int = Form(...),
    price: int = Form(...), # Price in cents
    db: Session = Depends(get_db),
    current_owner: schemas.Owner = Depends(get_current_owner)
):
    _ = i18n.gettext_locale(current_owner.locale)
    try:
        service_data = schemas.ServiceCreate(name=name, description=description, duration_minutes=duration_minutes, price=price)
        db_service = models.Service(**service_data.dict(), owner_id=current_owner.id)
        db.add(db_service)
        db.commit()
        db.refresh(db_service)
        return RedirectResponse(url="/dashboard?status=service_added", status_code=status.HTTP_303_SEE_OTHER)
    except Exception:
        return RedirectResponse(url=f"/dashboard?error={_('An error occurred while adding service.')}", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/dashboard/add_availability", response_class=RedirectResponse)
async def add_availability(
    request: Request,
    service_id: Optional[int] = Form(None),
    date_str: Optional[str] = Form(None),
    start_time_str: str = Form(...),
    end_time_str: str = Form(...),
    recurrence_type: Optional[str] = Form(None),
    recurrence_value: Optional[str] = Form(None),
    recurrence_start_date_str: Optional[str] = Form(None),
    recurrence_end_date_str: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_owner: schemas.Owner = Depends(get_current_owner)
):
    _ = i18n.gettext_locale(current_owner.locale)
    try:
        start_time = datetime.strptime(start_time_str, "%H:%M").time()
        end_time = datetime.strptime(end_time_str, "%H:%M").time()
        
        avail_date = datetime.strptime(date_str, "%Y-%m-%d").date() if date_str else None
        recur_start_date = datetime.strptime(recurrence_start_date_str, "%Y-%m-%d").date() if recurrence_start_date_str else None
        recur_end_date = datetime.strptime(recurrence_end_date_str, "%Y-%m-%d").date() if recurrence_end_date_str else None

        if recurrence_type and recurrence_type != "None":
            recurrence_enum = models.RecurrenceType[recurrence_type]
        else:
            recurrence_enum = None

        availability_data = schemas.AvailabilityCreate(
            service_id=service_id if service_id != 0 else None,
            date=avail_date,
            start_time=start_time,
            end_time=end_time,
            recurrence_type=recurrence_enum,
            recurrence_value=recurrence_value if recurrence_value else None,
            recurrence_start_date=recur_start_date,
            recurrence_end_date=recur_end_date
        )

        db_availability = models.Availability(**availability_data.dict(), owner_id=current_owner.id)
        db.add(db_availability)
        db.commit()
        db.refresh(db_availability)
        return RedirectResponse(url="/dashboard?status=availability_added", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        print(f"Error adding availability: {e}")
        return RedirectResponse(url=f"/dashboard?error={_('An error occurred while adding availability.')}", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/book/{owner_username}/{service_id}", response_class=HTMLResponse)
async def booking_page(
    owner_username: str,
    service_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    _ = i18n.gettext # Initialize gettext for this request

    owner = db.query(models.Owner).filter(models.Owner.username == owner_username).first()
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Owner not found"))

    service = db.query(models.Service).filter(models.Service.id == service_id, models.Service.owner_id == owner.id).first()
    if not service:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Service not found for this owner"))
    
    # Set locale for the public booking page based on owner's preference
    _ = i18n.gettext_locale(owner.locale)

    # Fetch available slots for today
    today = date.today()
    available_slots_today = availability_utils.get_available_slots_for_day(
        db, owner.id, service.id, today, service.duration_minutes
    )

    return templates.TemplateResponse(
        "booking_page.html",
        {
            "request": request,
            "owner": owner,
            "service": service,
            "today_date": today.isoformat(),
            "available_slots_today": [t.strftime("%H:%M") for t in available_slots_today],
            "gettext": _
        }
    )

@app.post("/book/{owner_username}/{service_id}", response_class=HTMLResponse)
async def create_booking(
    owner_username: str,
    service_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    try:
        form = await request.form()
        customer_name = form.get("customer_name")
        customer_email = form.get("customer_email")
        customer_phone = form.get("customer_phone")
        booking_date_str = form.get("booking_date")
        booking_time_str = form.get("booking_time")
        is_recurring_str = form.get("is_recurring")
        recurrence_type = form.get("recurrence_type")
        recurrence_value = form.get("recurrence_value")

        _ = i18n.gettext # Initialize gettext for this request

        owner = db.query(models.Owner).filter(models.Owner.username == owner_username).first()
        if not owner:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Owner not found"))

        service = db.query(models.Service).filter(models.Service.id == service_id, models.Service.owner_id == owner.id).first()
        if not service:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Service not found"))

        # Input validation
        if not all([customer_name, customer_email, booking_date_str, booking_time_str]):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_("Missing required booking information."))

        try:
            booking_date = datetime.strptime(booking_date_str, "%Y-%m-%d").date()
            booking_time = datetime.strptime(booking_time_str, "%H:%M").time()
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_("Invalid date or time format."))
        
        # Check if the slot is actually available
        available_slots = availability_utils.get_available_slots_for_day(
            db, owner.id, service.id, booking_date, service.duration_minutes
        )
        if booking_time not in available_slots:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_("Selected time slot is not available."))

        # --- Handle Customer Account (new logic) ---
        customer_id: Optional[int] = None
        existing_customer = db.query(models.Customer).filter(
            models.Customer.owner_id == owner.id,
            models.Customer.email == customer_email
        ).first()

        if existing_customer:
            customer_id = existing_customer.id
            # Update existing customer's name/phone if different
            if existing_customer.name != customer_name:
                existing_customer.name = customer_name
            if customer_phone and existing_customer.phone_number != customer_phone:
                existing_customer.phone_number = customer_phone
            db.add(existing_customer)
            db.commit()
            db.refresh(existing_customer)
        else:
            # Create a new customer if not found
            new_customer = models.Customer(
                owner_id=owner.id,
                name=customer_name,
                email=customer_email,
                phone_number=customer_phone
            )
            db.add(new_customer)
            db.commit()
            db.refresh(new_customer)
            customer_id = new_customer.id
        # --- End Customer Account logic ---

        is_recurring = is_recurring_str == "on"
        recurrence_id = None
        if is_recurring:
            if not all([recurrence_type, recurrence_value]):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_("Missing recurrence details for recurring booking."))
            recurrence_id = str(uuid.uuid4()) # Generate a unique ID for this recurrence series

        booking_data = schemas.BookingCreate(
            service_id=service.id,
            date=booking_date,
            time=booking_time,
            customer_name=customer_name, # Still store these for flexibility/non-customer bookings
            customer_email=customer_email,
            customer_phone=customer_phone,
            is_recurring=is_recurring,
            recurrence_id=recurrence_id,
            customer_id=customer_id # Pass the resolved customer_id
        )
        
        db_booking = models.Booking(**booking_data.dict(), owner_id=owner.id)
        db.add(db_booking)
        db.commit()
        db.refresh(db_booking)

        # Send notifications
        notifications.send_booking_confirmation(db_booking, owner, service)
        notifications.send_booking_notification_to_owner(db_booking, owner, service)

        # If recurring, create future bookings
        if is_recurring:
            create_recurring_bookings(db, owner, service, booking_data, recurrence_type, recurrence_value, db_booking.id)

        return templates.TemplateResponse(
            "booking_confirmation.html",
            {"request": request, "owner": owner, "service": service, "booking": db_booking, "gettext": i18n.gettext}
        )

    except HTTPException as e:
        # Render the booking page with an error message
        owner = db.query(models.Owner).filter(models.Owner.username == owner_username).first()
        service = db.query(models.Service).filter(models.Service.id == service_id, models.Service.owner_id == owner.id).first() if owner else None
        
        # Fetch current date's slots for display
        today = date.today()
        # Ensure service is not None before calling get_available_slots_for_day
        if owner and service:
            available_slots_today = availability_utils.get_available_slots_for_day(
                db, owner.id, service.id, today, service.duration_minutes
            )
        else:
            available_slots_today = []

        return templates.TemplateResponse(
            "booking_page.html",
            {
                "request": request,
                "owner": owner,
                "service": service,
                "error_message": e.detail,
                "today_date": today.isoformat(),
                "available_slots_today": [t.strftime("%H:%M") for t in available_slots_today],
                "gettext": i18n.gettext
            },
            status_code=e.status_code
        )
    except Exception as e:
        # Generic error handling
        print(f"An unexpected error occurred during booking: {e}")
        owner = db.query(models.Owner).filter(models.Owner.username == owner_username).first()
        service = db.query(models.Service).filter(models.Service.id == service_id, models.Service.owner_id == owner.id).first() if owner else None
        
        today = date.today()
        if owner and service:
            available_slots_today = availability_utils.get_available_slots_for_day(
                db, owner.id, service.id, today, service.duration_minutes
            )
        else:
            available_slots_today = []

        return templates.TemplateResponse(
            "booking_page.html",
            {
                "request": request,
                "owner": owner,
                "service": service,
                "error_message": _("An unexpected error occurred. Please try again."),
                "today_date": today.isoformat(),
                "available_slots_today": [t.strftime("%H:%M") for t in available_slots_today],
                "gettext": i18n.gettext
            },
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

# Stripe Webhook endpoint
@app.post("/stripe-webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get('stripe-signature')
    
    event = handle_webhook(payload, sig_header, db)
    
    return {"status": "success"}

# Owner subscription management page
@app.get("/subscription", response_class=HTMLResponse)
async def subscription_page(request: Request, db: Session = Depends(get_db), current_owner: schemas.Owner = Depends(get_current_owner)):
    _ = i18n.gettext_locale(current_owner.locale)
    return templates.TemplateResponse(
        "subscription.html",
        {
            "request": request,
            "owner": current_owner,
            "premium_price_id": settings.STRIPE_PREMIUM_PRICE_ID,
            "gettext": _
        }
    )

# Endpoint to create Stripe Checkout Session
@app.post("/create-checkout-session")
async def create_new_checkout_session(request: Request, db: Session = Depends(get_db), current_owner: schemas.Owner = Depends(get_current_owner)):
    _ = i18n.gettext_locale(current_owner.locale)
    if current_owner.subscription_status == "premium":
        raise HTTPException(status_code=400, detail=_("You are already on a premium plan."))
    
    try:
        session_id = create_checkout_session(current_owner, settings.STRIPE_PREMIUM_PRICE_ID)
        return schemas.StripeCheckoutSessionResponse(session_id=session_id)
    except Exception as e:
        print(f"Error creating checkout session: {e}")
        raise HTTPException(status_code=500, detail=_("Failed to create checkout session."))


app.include_router(router)
