from fastapi import FastAPI, Depends, HTTPException, status, Request, Response, APIRouter, Query, Form
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from jose import JWTError, jwt
from datetime import datetime, timedelta, date, time
from typing import List, Optional
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from gettext import gettext as _
from gettext import ngettext
import json
import os

from . import crud, models, schemas, security, notifications
from .database import SessionLocal, engine
from .config import settings
from .i18n import get_locale, activate_locale, get_translations_for_locale

models.Base.metadata.create_all(bind=engine)

app = FastAPI()

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Configure Jinja2Templates
templates = Jinja2Templates(directory="templates")

# Add translations to jinja2 environment
def _gettext(text): return _(text)
def _ngettext(singular, plural, n): return ngettext(singular, plural, n)
templates.env.globals['gettext'] = _gettext
templates.env.globals['ngettext'] = _ngettext
templates.env.globals['locale_dir'] = settings.LOCALES_DIR

# Add Session Middleware for language selection
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

@app.middleware("http")
async def setup_locale_middleware(request: Request, call_next):
    locale_code = request.session.get("locale", settings.DEFAULT_LOCALE)
    activate_locale(locale_code)
    request.state.locale = locale_code
    response = await call_next(request)
    return response

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

async def get_current_owner(db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=_("Could not validate credentials"),
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
    owner = crud.get_owner_by_email(db, email=token_data.email)
    if owner is None:
        raise credentials_exception
    return owner

async def get_current_active_owner(current_owner: schemas.Owner = Depends(get_current_owner)):
    if not current_owner.is_active:
        raise HTTPException(status_code=400, detail=_("Inactive owner"))
    return current_owner

# API Router for owner-specific routes
owner_router = APIRouter(prefix="/owner", tags=["owner"])

# API Router for admin routes
admin_router = APIRouter(prefix="/admin", tags=["admin"])

# Helper function to generate recurring slots
def generate_recurring_slots(
    start_time: time,
    end_time: time,
    service_duration: int,
    recurrence_type: str,
    recurrence_details: dict,
    start_date_range: date,
    end_date_range: date,
    availability_start_date: Optional[date] = None,
    availability_end_date: Optional[date] = None,
) -> List[datetime]:
    
    potential_slots = []
    current_date = start_date_range
    
    while current_date <= end_date_range:
        # Check if current_date is within the availability rule's own date range
        if availability_start_date and current_date < availability_start_date:
            current_date += timedelta(days=1)
            continue
        if availability_end_date and current_date > availability_end_date:
            # If the current date is past the availability rule's end date, we can stop
            # checking for this rule, as subsequent dates will also be past it.
            break
            
        is_available_on_this_day = False
        if recurrence_type == "daily":
            is_available_on_this_day = True
        elif recurrence_type == "weekly":
            # recurrence_details should contain 'days_of_week': [0, 1, ..., 6] (Monday=0, Sunday=6)
            if current_date.weekday() in recurrence_details.get("days_of_week", []):
                is_available_on_this_day = True
        elif recurrence_type == "monthly":
            # recurrence_details could contain 'day_of_month': N
            if current_date.day == recurrence_details.get("day_of_month"): # Simple monthly recurrence
                 is_available_on_this_day = True
        # Add other recurrence types (e.g., custom intervals) as needed

        if is_available_on_this_day:
            slot_start = datetime.combine(current_date, start_time)
            slot_end_boundary = datetime.combine(current_date, end_time)

            # Generate slots within the daily availability window
            while slot_start + timedelta(minutes=service_duration) <= slot_end_boundary:
                potential_slots.append(slot_start)
                slot_start += timedelta(minutes=service_duration)
        
        current_date += timedelta(days=1)
        
    return potential_slots

# --- Public Routes ---
@app.get("/", response_class=RedirectResponse, include_in_schema=False)
async def redirect_to_dashboard():
    return RedirectResponse(url="/owner/dashboard")

@app.post("/token", response_model=schemas.Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    owner = security.authenticate_owner(db, form_data.username, form_data.password)
    if not owner:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_("Incorrect email or password"),
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": owner.email}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/signup", response_model=schemas.Owner)
async def owner_signup(owner: schemas.OwnerCreate, db: Session = Depends(get_db)):
    db_owner = crud.get_owner_by_email(db, email=owner.email)
    if db_owner:
        raise HTTPException(status_code=400, detail=_("Email already registered"))
    return crud.create_owner(db=db, owner=owner)

@app.get("/lang/{locale_code}")
async def set_language(locale_code: str, request: Request, response: Response):
    request.session["locale"] = locale_code
    # Redirect to the page where the user came from, or a default if not available
    referer = request.headers.get("referer", "/")
    return RedirectResponse(url=referer)

@app.get("/bookslot.app/{owner_name}", response_class=Response, include_in_schema=False)
async def public_booking_page_by_owner_name(
    owner_name: str,
    request: Request,
    db: Session = Depends(get_db)
):
    # This endpoint needs to be adjusted based on how owner_name maps to an owner
    # For now, let's assume owner_name is actually owner.company_name or a slug
    # This is a placeholder for the actual logic to retrieve owner and their services
    owner = db.query(models.Owner).filter(models.Owner.company_name == owner_name).first()
    if not owner:
        raise HTTPException(status_code=404, detail=_("Booking page not found"))
    
    services = crud.get_services(db, owner_id=owner.id)
    
    # Pass services data to the template
    return templates.TemplateResponse(
        "booking_page.html", 
        {"request": request, "owner": owner, "services": services, "_": request.app.extra["gettext"]}
    )

@app.get("/services/{service_id}/available-slots", response_model=List[datetime])
async def get_service_available_slots(
    service_id: int,
    start_date: date = Query(..., description="Start date for availability check (YYYY-MM-DD)"),
    end_date: date = Query(..., description="End date for availability check (YYYY-MM-DD)"),
    db: Session = Depends(get_db)
):
    service = crud.get_service(db, service_id=service_id)
    if not service:
        raise HTTPException(status_code=404, detail=_("Service not found"))

    service_duration = service.duration_minutes

    all_potential_slots = []
    
    # Fetch all availability rules for this service
    availabilities = crud.get_service_availabilities(db, service_id=service_id)
    
    for avail in availabilities:
        if avail.is_recurring and avail.recurrence_type and avail.recurrence_details:
            try:
                recurrence_details_dict = json.loads(avail.recurrence_details)
            except json.JSONDecodeError:
                # Handle malformed JSON, perhaps log and skip this availability rule
                print(f"Warning: Malformed recurrence_details for availability ID {avail.id}")
                continue
            
            # Generate slots based on recurrence
            recurring_slots = generate_recurring_slots(
                start_time=avail.start_time,
                end_time=avail.end_time,
                service_duration=service_duration,
                recurrence_type=avail.recurrence_type,
                recurrence_details=recurrence_details_dict,
                start_date_range=start_date,
                end_date_range=end_date,
                availability_start_date=avail.start_date,
                availability_end_date=avail.end_date
            )
            all_potential_slots.extend(recurring_slots)
        else:
            # Handle non-recurring, specific date availabilities
            # For a non-recurring availability, it's only available on its specific start_date
            # if start_date is provided and falls within the requested range.
            if avail.start_date and start_date <= avail.start_date <= end_date:
                slot_start_dt = datetime.combine(avail.start_date, avail.start_time)
                slot_end_boundary_dt = datetime.combine(avail.start_date, avail.end_time)
                
                current_slot_start = slot_start_dt
                while current_slot_start + timedelta(minutes=service_duration) <= slot_end_boundary_dt:
                    all_potential_slots.append(current_slot_start)
                    current_slot_start += timedelta(minutes=service_duration)

    # Remove duplicates and sort
    all_potential_slots = sorted(list(set(all_potential_slots)))

    # Fetch existing bookings for the service within the date range
    existing_bookings = crud.get_bookings_for_service_in_range(db, service_id, start_date, end_date)

    available_slots = []
    for slot_start_dt in all_potential_slots:
        slot_end_dt = slot_start_dt + timedelta(minutes=service_duration)
        is_booked = False
        for booking in existing_bookings:
            booking_start_dt = booking.start_time
            booking_end_dt = booking.end_time
            
            # Check for overlap: If the slot's end is not before booking's start AND slot's start is not after booking's end
            if not (slot_end_dt <= booking_start_dt or slot_start_dt >= booking_end_dt):
                is_booked = True
                break
        
        if not is_booked:
            available_slots.append(slot_start_dt)

    return available_slots

@app.post("/bookslot.app/{owner_name}/book", response_class=Response)
async def submit_booking(
    owner_name: str, 
    request: Request,
    service_id: int = Form(...),
    customer_name: str = Form(...),
    customer_email: str = Form(...),
    customer_phone: Optional[str] = Form(None),
    start_time_str: str = Form(...), # Expecting ISO format string
    db: Session = Depends(get_db)
):
    owner = db.query(models.Owner).filter(models.Owner.company_name == owner_name).first()
    if not owner:
        raise HTTPException(status_code=404, detail=_("Booking page not found"))

    service = crud.get_service(db, service_id=service_id)
    if not service or service.owner_id != owner.id:
        raise HTTPException(status_code=404, detail=_("Service not found for this owner"))

    try:
        start_time = datetime.fromisoformat(start_time_str)
    except ValueError:
        raise HTTPException(status_code=400, detail=_("Invalid start time format"))

    # Validate if the chosen slot is actually available
    # This is a critical check to prevent double bookings
    # We need to re-run the availability logic for the chosen date
    # The date range for this check should encompass the single day of the booking
    available_slots_for_day = await get_service_available_slots(service_id, start_time.date(), start_time.date(), db)
    if start_time not in available_slots_for_day:
        raise HTTPException(status_code=400, detail=_("Chosen slot is no longer available. Please refresh and try again."))

    booking_schema = schemas.BookingCreate(
        service_id=service.id,
        customer_name=customer_name,
        customer_email=customer_email,
        customer_phone=customer_phone,
        start_time=start_time
    )
    
    try:
        db_booking = crud.create_booking(db=db, booking=booking_schema, owner_id=owner.id, service_duration_minutes=service.duration_minutes)
        
        # Send email notifications
        notifications.send_booking_confirmation_email(owner, service, db_booking)
        notifications.send_customer_confirmation_email(owner, service, db_booking)
        # Send WhatsApp notifications (if configured)
        notifications.send_whatsapp_notification(owner, service, db_booking)

        return templates.TemplateResponse(
            "booking_confirmation.html", 
            {"request": request, "booking": db_booking, "service": service, "owner": owner, "_gettext": request.app.extra["gettext"]}
        )
    except Exception as e:
        # Log the error for debugging
        print(f"Error creating booking: {e}")
        raise HTTPException(status_code=500, detail=_("An error occurred while processing your booking. Please try again."))

# --- Owner Dashboard Routes ---
@owner_router.get("/dashboard", response_class=Response)
async def owner_dashboard(request: Request, db: Session = Depends(get_db), current_owner: schemas.Owner = Depends(get_current_active_owner)):
    bookings = crud.get_bookings(db, owner_id=current_owner.id)
    services = crud.get_services(db, owner_id=current_owner.id)

    # Analytics for current month
    today = date.today()
    start_of_month = datetime(today.year, today.month, 1)
    end_of_month = (start_of_month + timedelta(days=32)).replace(day=1) # First day of next month

    total_bookings_month = crud.get_total_bookings_month(db, current_owner.id, start_of_month, end_of_month)
    popular_services = crud.get_popular_services(db, current_owner.id, start_of_month, end_of_month)

    return templates.TemplateResponse(
        "dashboard.html", 
        {
            "request": request,
            "owner": current_owner,
            "bookings": bookings,
            "services": services,
            "total_bookings_month": total_bookings_month,
            "popular_services": popular_services,
            "_gettext": request.app.extra["gettext"],
            "locale": request.state.locale
        }
    )

@owner_router.post("/update-profile", response_model=schemas.Owner)
async def update_owner_profile(
    request: Request,
    db: Session = Depends(get_db),
    current_owner: schemas.Owner = Depends(get_current_active_owner),
    email: EmailStr = Form(...),
    company_name: Optional[str] = Form(None),
    phone: Optional[str] = Form(None)
):
    owner_update = schemas.OwnerUpdate(email=email, company_name=company_name, phone=phone)
    try:
        updated_owner = crud.update_owner(db, current_owner, owner_update)
        return templates.TemplateResponse(
            "dashboard.html", 
            {
                "request": request, 
                "owner": updated_owner, 
                "bookings": crud.get_bookings(db, owner_id=updated_owner.id), # Refresh data
                "services": crud.get_services(db, owner_id=updated_owner.id), # Refresh data
                "_gettext": request.app.extra["gettext"],
                "locale": request.state.locale,
                "message": _("Profile updated successfully!")
            }
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@owner_router.get("/services", response_model=List[schemas.Service])
async def read_owner_services(
    db: Session = Depends(get_db),
    current_owner: schemas.Owner = Depends(get_current_active_owner)
):
    services = crud.get_services(db, owner_id=current_owner.id)
    return services

@owner_router.post("/services", response_model=schemas.Service)
async def create_owner_service(
    service: schemas.ServiceCreate,
    db: Session = Depends(get_db),
    current_owner: schemas.Owner = Depends(get_current_active_owner)
):
    return crud.create_owner_service(db=db, service=service, owner_id=current_owner.id)

@owner_router.get("/services/{service_id}", response_model=schemas.Service)
async def read_owner_service(
    service_id: int,
    db: Session = Depends(get_db),
    current_owner: schemas.Owner = Depends(get_current_active_owner)
):
    db_service = crud.get_service_by_owner(db, service_id=service_id, owner_id=current_owner.id)
    if db_service is None:
        raise HTTPException(status_code=404, detail=_("Service not found"))
    return db_service

@owner_router.put("/services/{service_id}", response_model=schemas.Service)
async def update_owner_service(
    service_id: int,
    service: schemas.ServiceCreate,
    db: Session = Depends(get_db),
    current_owner: schemas.Owner = Depends(get_current_active_owner)
):
    db_service = crud.get_service_by_owner(db, service_id=service_id, owner_id=current_owner.id)
    if db_service is None:
        raise HTTPException(status_code=404, detail=_("Service not found"))
    return crud.update_service(db=db, db_service=db_service, service_update=service)

@owner_router.delete("/services/{service_id}")
async def delete_owner_service(
    service_id: int,
    db: Session = Depends(get_db),
    current_owner: schemas.Owner = Depends(get_current_active_owner)
):
    db_service = crud.get_service_by_owner(db, service_id=service_id, owner_id=current_owner.id)
    if db_service is None:
        raise HTTPException(status_code=404, detail=_("Service not found"))
    if crud.delete_service(db=db, service_id=service_id):
        return {"message": _("Service deleted successfully")} 
    raise HTTPException(status_code=500, detail=_("Could not delete service"))

@owner_router.get("/services/{service_id}/availabilities", response_model=List[schemas.Availability])
async def read_service_availabilities(
    service_id: int,
    db: Session = Depends(get_db),
    current_owner: schemas.Owner = Depends(get_current_active_owner)
):
    service = crud.get_service_by_owner(db, service_id=service_id, owner_id=current_owner.id)
    if not service:
        raise HTTPException(status_code=404, detail=_("Service not found"))
    return crud.get_service_availabilities(db, service_id=service_id)

@owner_router.post("/services/{service_id}/availabilities", response_model=schemas.Availability)
async def create_service_availability(
    service_id: int,
    availability: schemas.AvailabilityCreate,
    db: Session = Depends(get_db),
    current_owner: schemas.Owner = Depends(get_current_active_owner)
):
    service = crud.get_service_by_owner(db, service_id=service_id, owner_id=current_owner.id)
    if not service:
        raise HTTPException(status_code=404, detail=_("Service not found"))
    return crud.create_service_availability(db=db, availability=availability, owner_id=current_owner.id, service_id=service_id)

@owner_router.put("/availabilities/{availability_id}", response_model=schemas.Availability)
async def update_service_availability(
    availability_id: int,
    availability: schemas.AvailabilityCreate,
    db: Session = Depends(get_db),
    current_owner: schemas.Owner = Depends(get_current_active_owner)
):
    db_availability = crud.get_availability(db, availability_id=availability_id)
    if not db_availability or db_availability.owner_id != current_owner.id:
        raise HTTPException(status_code=404, detail=_("Availability not found"))
    return crud.update_availability(db=db, db_availability=db_availability, availability_update=availability)

@owner_router.delete("/availabilities/{availability_id}")
async def delete_service_availability(
    availability_id: int,
    db: Session = Depends(get_db),
    current_owner: schemas.Owner = Depends(get_current_active_owner)
):
    db_availability = crud.get_availability(db, availability_id=availability_id)
    if not db_availability or db_availability.owner_id != current_owner.id:
        raise HTTPException(status_code=404, detail=_("Availability not found"))
    if crud.delete_availability(db=db, availability_id=availability_id):
        return {"message": _("Availability deleted successfully")} 
    raise HTTPException(status_code=500, detail=_("Could not delete availability"))

@owner_router.get("/bookings", response_model=List[schemas.Booking])
async def read_owner_bookings(
    db: Session = Depends(get_db),
    current_owner: schemas.Owner = Depends(get_current_active_owner)
):
    bookings = crud.get_bookings(db, owner_id=current_owner.id)
    return bookings

@owner_router.get("/bookings/{booking_id}", response_model=schemas.Booking)
async def read_owner_booking(
    booking_id: int,
    db: Session = Depends(get_db),
    current_owner: schemas.Owner = Depends(get_current_active_owner)
):
    db_booking = crud.get_booking(db, booking_id=booking_id)
    if db_booking is None or db_booking.owner_id != current_owner.id:
        raise HTTPException(status_code=404, detail=_("Booking not found"))
    return db_booking

@owner_router.put("/bookings/{booking_id}", response_model=schemas.Booking)
async def update_owner_booking(
    booking_id: int,
    booking: schemas.BookingCreate, # This schema might need refinement for update scenarios
    db: Session = Depends(get_db),
    current_owner: schemas.Owner = Depends(get_current_active_owner)
):
    db_booking = crud.get_booking(db, booking_id=booking_id)
    if db_booking is None or db_booking.owner_id != current_owner.id:
        raise HTTPException(status_code=404, detail=_("Booking not found"))
    
    # Fetch service duration to recalculate end_time if start_time is updated
    service = crud.get_service(db, service_id=db_booking.service_id)
    if not service:
        raise HTTPException(status_code=404, detail=_("Associated service not found"))

    # Pass service_duration_minutes to the crud function for recalculation
    booking_update_data = booking.model_dump()
    booking_update_data["service_duration_minutes"] = service.duration_minutes

    return crud.update_booking(db=db, db_booking=db_booking, booking_update=schemas.BookingCreate(**booking_update_data))

@owner_router.delete("/bookings/{booking_id}")
async def delete_owner_booking(
    booking_id: int,
    db: Session = Depends(get_db),
    current_owner: schemas.Owner = Depends(get_current_active_owner)
):
    db_booking = crud.get_booking(db, booking_id=booking_id)
    if db_booking is None or db_booking.owner_id != current_owner.id:
        raise HTTPException(status_code=404, detail=_("Booking not found"))
    if crud.delete_booking(db=db, booking_id=booking_id):
        return {"message": _("Booking deleted successfully")} 
    raise HTTPException(status_code=500, detail=_("Could not delete booking"))

# --- Analytics API Endpoint ---
@owner_router.get("/analytics", response_model=schemas.AnalyticsData)
async def get_owner_analytics(
    db: Session = Depends(get_db),
    current_owner: schemas.Owner = Depends(get_current_active_owner)
):
    today = date.today()
    start_of_month = datetime(today.year, today.month, 1)
    end_of_month = (start_of_month + timedelta(days=32)).replace(day=1) # First day of next month

    total_bookings_month = crud.get_total_bookings_month(db, current_owner.id, start_of_month, end_of_month)
    popular_services = crud.get_popular_services(db, current_owner.id, start_of_month, end_of_month)

    return schemas.AnalyticsData(
        total_bookings_month=total_bookings_month,
        popular_services=popular_services
    )

# --- Stripe Payment Gateway --- #

@owner_router.post("/create-checkout-session", response_model=schemas.StripeCheckoutSession)
async def create_checkout_session(request: Request, current_owner: schemas.Owner = Depends(get_current_active_owner)):
    try:
        checkout_session = notifications.stripe.checkout.Session.create(
            line_items=[
                {
                    "price": settings.STRIPE_PRICE_ID,
                    "quantity": 1,
                }
            ],
            mode="subscription",
            success_url=f"{settings.SERVER_NAME}/owner/dashboard?success=true",
            cancel_url=f"{settings.SERVER_NAME}/owner/dashboard?canceled=true",
            customer_email=current_owner.email,
            client_reference_id=str(current_owner.id)
        )
        return schemas.StripeCheckoutSession(url=checkout_session.url)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/stripe-webhook")
async def stripe_webhook(request: Request):
    event = None
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = notifications.stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError as e:
        # Invalid payload
        raise HTTPException(status_code=400, detail=str(e))
    except notifications.stripe.error.SignatureVerificationError as e:
        # Invalid signature
        raise HTTPException(status_code=400, detail=str(e))

    # Handle the event
    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        owner_id = session.get("client_reference_id")
        customer_email = session.get("customer_details", {}).get("email")
        subscription_id = session.get("subscription")
        
        print(f"Checkout session completed for owner {owner_id} ({customer_email}). Subscription ID: {subscription_id}")
        # Here you would typically update your database to mark the owner as a premium subscriber
        # For example, create a Subscription model and link it to the Owner.

    elif event["type"] == "invoice.payment_succeeded":
        invoice = event["data"]["object"]
        print(f"Invoice payment succeeded for customer {invoice.get('customer')}")
        # Handle successful recurring payments

    elif event["type"] == "customer.subscription.deleted":
        subscription = event["data"]["object"]
        print(f"Subscription deleted for customer {subscription.get('customer')}")
        # Handle subscription cancellation/deletion

    return Response(status_code=200)

# --- Admin Routes ---
@admin_router.get("/owners", response_model=List[schemas.Owner])
async def admin_read_owners(
    db: Session = Depends(get_db),
    current_owner: schemas.Owner = Depends(get_current_active_owner) # Admin check needed
):
    # For a real admin panel, this would need proper admin role checking
    # For now, any logged-in owner can access, which is NOT PRODUCTION READY.
    return crud.admin_get_owners(db)

@admin_router.get("/owners/{owner_id}", response_model=schemas.Owner)
async def admin_read_owner(
    owner_id: int,
    db: Session = Depends(get_db),
    current_owner: schemas.Owner = Depends(get_current_active_owner)
):
    db_owner = crud.admin_get_owner(db, owner_id=owner_id)
    if db_owner is None:
        raise HTTPException(status_code=404, detail=_("Owner not found"))
    return db_owner

@admin_router.put("/owners/{owner_id}", response_model=schemas.Owner)
async def admin_update_owner(
    owner_id: int,
    owner_update: schemas.AdminOwnerUpdate,
    db: Session = Depends(get_db),
    current_owner: schemas.Owner = Depends(get_current_active_owner)
):
    db_owner = crud.admin_get_owner(db, owner_id=owner_id)
    if db_owner is None:
        raise HTTPException(status_code=404, detail=_("Owner not found"))
    return crud.admin_update_owner(db, db_owner, owner_update)

@admin_router.delete("/owners/{owner_id}")
async def admin_delete_owner(
    owner_id: int,
    db: Session = Depends(get_db),
    current_owner: schemas.Owner = Depends(get_current_active_owner)
):
    if crud.admin_delete_owner(db, owner_id):
        return {"message": _("Owner deleted successfully")} 
    raise HTTPException(status_code=404, detail=_("Owner not found"))

@admin_router.get("/owners/{owner_id}/services", response_model=List[schemas.Service])
async def admin_read_services_by_owner(
    owner_id: int,
    db: Session = Depends(get_db),
    current_owner: schemas.Owner = Depends(get_current_active_owner)
):
    owner = crud.admin_get_owner(db, owner_id=owner_id)
    if not owner:
        raise HTTPException(status_code=404, detail=_("Owner not found"))
    return crud.admin_get_services_by_owner(db, owner_id=owner_id)

@admin_router.put("/services/{service_id}", response_model=schemas.Service)
async def admin_update_service(
    service_id: int,
    service_update: schemas.AdminServiceUpdate,
    db: Session = Depends(get_db),
    current_owner: schemas.Owner = Depends(get_current_active_owner)
):
    db_service = crud.admin_get_service(db, service_id=service_id)
    if db_service is None:
        raise HTTPException(status_code=404, detail=_("Service not found"))
    return crud.admin_update_service(db, db_service, service_update)

@admin_router.delete("/services/{service_id}")
async def admin_delete_service(
    service_id: int,
    db: Session = Depends(get_db),
    current_owner: schemas.Owner = Depends(get_current_active_owner)
):
    if crud.admin_delete_service(db, service_id):
        return {"message": _("Service deleted successfully")} 
    raise HTTPException(status_code=404, detail=_("Service not found"))

@admin_router.get("/owners/{owner_id}/bookings", response_model=List[schemas.Booking])
async def admin_read_bookings_by_owner(
    owner_id: int,
    db: Session = Depends(get_db),
    current_owner: schemas.Owner = Depends(get_current_active_owner)
):
    owner = crud.admin_get_owner(db, owner_id=owner_id)
    if not owner:
        raise HTTPException(status_code=404, detail=_("Owner not found"))
    return crud.admin_get_bookings_by_owner(db, owner_id=owner_id)

@admin_router.put("/bookings/{booking_id}", response_model=schemas.Booking)
async def admin_update_booking(
    booking_id: int,
    booking_update: schemas.AdminBookingUpdate,
    db: Session = Depends(get_db),
    current_owner: schemas.Owner = Depends(get_current_active_owner)
):
    db_booking = crud.admin_get_booking(db, booking_id=booking_id)
    if db_booking is None:
        raise HTTPException(status_code=404, detail=_("Booking not found"))
    return crud.admin_update_booking(db, db_booking, booking_update)

@admin_router.delete("/bookings/{booking_id}")
async def admin_delete_booking(
    booking_id: int,
    db: Session = Depends(get_db),
    current_owner: schemas.Owner = Depends(get_current_active_owner)
):
    if crud.admin_delete_booking(db, booking_id):
        return {"message": _("Booking deleted successfully")} 
    raise HTTPException(status_code=404, detail=_("Booking not found"))

app.include_router(owner_router)
app.include_router(admin_router)
