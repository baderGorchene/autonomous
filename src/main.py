from fastapi import FastAPI, Depends, HTTPException, status, Request, Response
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from typing import Annotated, Dict, Any, List
from datetime import timedelta, datetime, date, time
import json

from src import schemas, crud, models, security
from src.database import create_tables, get_db
from src.config import settings
from src.dependencies import get_current_owner
from src.notifications import send_booking_confirmation_email, send_owner_notification_email, send_whatsapp_message
from src.i18n import _, set_locale, get_locale

from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware

import logging

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = FastAPI()

# Add Session Middleware for language selection (and potentially other session data)
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

# Initialize Jinja2Templates
templates = Jinja2Templates(directory="templates")

# Add gettext to Jinja2 environment
def init_jinja2_env():
    templates.env.globals['gettext'] = _
    templates.env.globals['current_locale'] = get_locale
    templates.env.filters['currency_format'] = lambda value, currency_code: f"{value:.2f} {currency_code}" # Placeholder for more complex formatting

@app.on_event("startup")
def on_startup():
    create_tables()
    init_jinja2_env()

# Dependency to set locale from session or header
@app.middleware("http")
async def set_locale_middleware(request: Request, call_next):
    locale_code = request.session.get("locale", "en")
    
    # Check for language query parameter (e.g., ?lang=ar)
    lang_param = request.query_params.get("lang")
    if lang_param and lang_param in ["en", "ar", "fr"]:
        locale_code = lang_param
        request.session["locale"] = locale_code

    set_locale(locale_code)
    response = await call_next(request)
    return response

@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    try:
        # Attempt a simple query to check DB connectivity
        db.execute(models.text("SELECT 1"))
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        raise HTTPException(status_code=500, detail="Database connection failed")

@app.post("/token", response_model=schemas.Token)
async def login_for_access_token(form_data: Annotated[OAuth2PasswordRequestForm, Depends()], db: Session = Depends(get_db)):
    owner = crud.authenticate_owner(db, form_data.username, form_data.password)
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

@app.post("/owner/signup", response_model=schemas.Owner)
def create_owner_account(owner: schemas.OwnerCreate, db: Session = Depends(get_db)):
    db_owner = crud.get_owner_by_email(db, email=owner.email)
    if db_owner:
        raise HTTPException(status_code=400, detail="Email already registered")
    db_owner = crud.get_owner_by_slug(db, slug=owner.slug)
    if db_owner:
        raise HTTPException(status_code=400, detail="Business URL already taken")
    return crud.create_owner(db=db, owner=owner)

@app.get("/owner/me", response_model=schemas.Owner)
async def read_owners_me(current_owner: Annotated[models.Owner, Depends(get_current_owner)]):
    return current_owner

@app.get("/dashboard", response_class=HTMLResponse)
async def owner_dashboard(request: Request, current_owner: Annotated[models.Owner, Depends(get_current_owner)], db: Session = Depends(get_db)):
    bookings = crud.get_owner_bookings(db, owner_id=current_owner.id)
    # Convert JSON strings back to Python objects for display
    services = json.loads(current_owner.services_json) if current_owner.services_json else []
    availability = json.loads(current_owner.availability_json) if current_owner.availability_json else {}

    # Filter bookings to only show upcoming ones
    today = date.today()
    now = datetime.now().time()
    upcoming_bookings = []
    for booking in bookings:
        booking_datetime = datetime.combine(booking.booking_date, booking.booking_time)
        if booking_datetime > datetime.now():
            upcoming_bookings.append(booking)
    
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "owner": current_owner,
            "services": services,
            "availability": availability,
            "bookings": upcoming_bookings,
            "_" : _,
            "current_locale": get_locale()
        }
    )

@app.post("/dashboard/profile", response_class=HTMLResponse)
async def update_owner_profile_route(
    request: Request,
    owner_update: schemas.OwnerProfileUpdate = Depends(schemas.OwnerProfileUpdate.as_form),
    current_owner: Annotated[models.Owner, Depends(get_current_owner)],
    db: Session = Depends(get_db)
):
    try:
        updated_owner = crud.update_owner_profile(db, current_owner, owner_update)
        # Re-fetch bookings and other data for the template
        bookings = crud.get_owner_bookings(db, owner_id=updated_owner.id)
        services = json.loads(updated_owner.services_json) if updated_owner.services_json else []
        availability = json.loads(updated_owner.availability_json) if updated_owner.availability_json else {}

        today = date.today()
        now = datetime.now().time()
        upcoming_bookings = []
        for booking in bookings:
            booking_datetime = datetime.combine(booking.booking_date, booking.booking_time)
            if booking_datetime > datetime.now():
                upcoming_bookings.append(booking)

        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "owner": updated_owner,
                "services": services,
                "availability": availability,
                "bookings": upcoming_bookings,
                "message": _("Profile updated successfully!"),
                "_" : _,
                "current_locale": get_locale()
            }
        )
    except Exception as e:
        logger.error(f"Error updating profile: {e}")
        raise HTTPException(status_code=500, detail=_("Failed to update profile."))

@app.post("/dashboard/services", response_class=HTMLResponse)
async def update_owner_services(
    request: Request,
    service_name: str = Depends(lambda n: n if n else None),
    service_duration: int = Depends(lambda d: int(d) if d else None),
    service_price: float = Depends(lambda p: float(p) if p else None),
    action: str = Depends(lambda a: a if a else None),
    service_index: int = Depends(lambda i: int(i) if i else None),
    current_owner: Annotated[models.Owner, Depends(get_current_owner)],
    db: Session = Depends(get_db)
):
    services = json.loads(current_owner.services_json) if current_owner.services_json else []
    message = ""
    error = ""

    if action == "add":
        if service_name and service_duration and service_price is not None:
            services.append({"name": service_name, "duration": service_duration, "price": service_price})
            message = _("Service added successfully!")
        else:
            error = _("All service fields are required to add a service.")
    elif action == "delete":
        if service_index is not None and 0 <= service_index < len(services):
            del services[service_index]
            message = _("Service deleted successfully!")
        else:
            error = _("Invalid service index for deletion.")
    
    if not error:
        current_owner.services_json = json.dumps(services)
        db.add(current_owner)
        db.commit()
        db.refresh(current_owner)

    # Re-fetch data for the template
    bookings = crud.get_owner_bookings(db, owner_id=current_owner.id)
    availability = json.loads(current_owner.availability_json) if current_owner.availability_json else {}
    upcoming_bookings = [b for b in bookings if datetime.combine(b.booking_date, b.booking_time) > datetime.now()]

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "owner": current_owner,
            "services": services,
            "availability": availability,
            "bookings": upcoming_bookings,
            "message": message,
            "error": error,
            "_" : _,
            "current_locale": get_locale()
        }
    )

@app.post("/dashboard/availability", response_class=HTMLResponse)
async def update_owner_availability(
    request: Request,
    day_of_week: str = Depends(lambda d: d if d else None),
    start_time: str = Depends(lambda s: s if s else None),
    end_time: str = Depends(lambda e: e if e else None),
    action: str = Depends(lambda a: a if a else None),
    time_slot_index: int = Depends(lambda i: int(i) if i else None),
    current_owner: Annotated[models.Owner, Depends(get_current_owner)],
    db: Session = Depends(get_db)
):
    availability = json.loads(current_owner.availability_json) if current_owner.availability_json else {}
    message = ""
    error = ""

    if action == "add":
        if day_of_week and start_time and end_time:
            if day_of_week not in availability:
                availability[day_of_week] = []
            availability[day_of_week].append({"start": start_time, "end": end_time})
            message = _("Availability added successfully!")
        else:
            error = _("All availability fields are required to add a time slot.")
    elif action == "delete":
        if day_of_week and time_slot_index is not None and day_of_week in availability and 0 <= time_slot_index < len(availability[day_of_week]):
            del availability[day_of_week][time_slot_index]
            if not availability[day_of_week]: # If no slots left for the day, remove the day
                del availability[day_of_week]
            message = _("Availability slot deleted successfully!")
        else:
            error = _("Invalid availability slot for deletion.")
    
    if not error:
        current_owner.availability_json = json.dumps(availability)
        db.add(current_owner)
        db.commit()
        db.refresh(current_owner)

    # Re-fetch data for the template
    bookings = crud.get_owner_bookings(db, owner_id=current_owner.id)
    services = json.loads(current_owner.services_json) if current_owner.services_json else []
    upcoming_bookings = [b for b in bookings if datetime.combine(b.booking_date, b.booking_time) > datetime.now()]

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "owner": current_owner,
            "services": services,
            "availability": availability,
            "bookings": upcoming_bookings,
            "message": message,
            "error": error,
            "_" : _,
            "current_locale": get_locale()
        }
    )


@app.get("/{owner_slug}", response_class=HTMLResponse)
async def booking_page(request: Request, owner_slug: str, db: Session = Depends(get_db)):
    owner = crud.get_owner_by_slug(db, slug=owner_slug)
    if not owner:
        raise HTTPException(status_code=404, detail=_("Owner not found"))
    
    services = json.loads(owner.services_json) if owner.services_json else []
    availability = json.loads(owner.availability_json) if owner.availability_json else {}

    # Generate available dates for the next 30 days
    available_dates = []
    for i in range(30):
        current_date = date.today() + timedelta(days=i)
        day_of_week = current_date.strftime('%A').lower() # e.g., 'monday'
        if day_of_week in availability:
            available_dates.append(current_date.isoformat())

    return templates.TemplateResponse(
        "booking_page.html", 
        {
            "request": request, 
            "owner": owner, 
            "services": services,
            "availability": availability,
            "available_dates": available_dates,
            "_" : _,
            "current_locale": get_locale()
        }
    )

@app.post("/{owner_slug}/book", response_class=HTMLResponse)
async def submit_booking(
    request: Request,
    owner_slug: str,
    customer_name: str = Depends(lambda n: n if n else None),
    customer_email: str = Depends(lambda e: e if e else None),
    customer_phone: str = Depends(lambda p: p if p else None),
    service_name: str = Depends(lambda sn: sn if sn else None),
    booking_date: date = Depends(lambda bd: date.fromisoformat(bd) if bd else None),
    booking_time: time = Depends(lambda bt: time.fromisoformat(bt) if bt else None),
    db: Session = Depends(get_db)
):
    owner = crud.get_owner_by_slug(db, slug=owner_slug)
    if not owner:
        raise HTTPException(status_code=404, detail=_("Owner not found"))

    # Basic validation
    if not all([customer_name, customer_email, service_name, booking_date, booking_time]):
        return templates.TemplateResponse(
            "booking_page.html",
            {
                "request": request, 
                "owner": owner, 
                "services": json.loads(owner.services_json),
                "availability": json.loads(owner.availability_json),
                "error": _("Please fill in all required fields."),
                "_" : _,
                "current_locale": get_locale()
            },
            status_code=400
        )
    
    # More sophisticated availability check (e.g., prevent double booking, check against owner's set availability)
    # For MVP, we assume the selected time from the UI is valid based on the owner's availability
    # A real system would re-verify on the backend.

    booking_data = schemas.BookingCreate(
        customer_name=customer_name,
        customer_email=customer_email,
        customer_phone=customer_phone,
        service_name=service_name,
        booking_date=booking_date,
        booking_time=booking_time,
        status="pending"
    )

    try:
        db_booking = crud.create_booking(db=db, booking=booking_data, owner_id=owner.id)
        
        # Send notifications
        booking_details = {
            "customer_name": db_booking.customer_name,
            "customer_email": db_booking.customer_email,
            "customer_phone": db_booking.customer_phone,
            "service_name": db_booking.service_name,
            "booking_date": db_booking.booking_date.isoformat(),
            "booking_time": db_booking.booking_time.isoformat(),
            "owner_name": owner.name,
            "owner_email": owner.email,
            "owner_phone": owner.phone
        }

        send_booking_confirmation_email(booking_details)
        send_owner_notification_email(booking_details)
        if owner.phone: # Only send WhatsApp if owner has provided a phone number
            send_whatsapp_message(booking_details)

        return templates.TemplateResponse(
            "booking_confirmation.html", 
            {
                "request": request, 
                "booking": db_booking, 
                "owner": owner,
                "_" : _,
                "current_locale": get_locale()
            }
        )
    except Exception as e:
        logger.error(f"Error creating booking: {e}")
        return templates.TemplateResponse(
            "booking_page.html",
            {
                "request": request, 
                "owner": owner, 
                "services": json.loads(owner.services_json),
                "availability": json.loads(owner.availability_json),
                "error": _("An unexpected error occurred. Please try again later."),
                "_" : _,
                "current_locale": get_locale()
            },
            status_code=500
        )

@app.get("/static/{filepath:path}")
async def static_files(filepath: str):
    # This is a placeholder for serving static files.
    # In a real deployment, a web server like Nginx would serve static files directly.
    # For local development, you might use StaticFiles from fastapi.staticfiles
    # For now, we'll just raise a 404.
    raise HTTPException(status_code=404, detail="Static file not found")
