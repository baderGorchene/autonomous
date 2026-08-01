from fastapi import FastAPI, Depends, HTTPException, status, Request, Response, Form
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta, date, datetime
from typing import List, Dict, Any, Optional
import json
import os
import logging

from . import models, schemas, crud, security, notifications
from .database import SessionLocal, engine, create_tables, get_db
from .config import settings
from .i18n_config import get_jinja_env # Import the configured Jinja2 environment

# Initialize logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create database tables on startup (if they don't exist)
create_tables()

app = FastAPI()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Dependency to get current owner from JWT token
async def get_current_owner(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    email = security.decode_access_token(token)
    if email is None:
        raise credentials_exception
    owner = crud.get_owner_by_email(db, email=email)
    if owner is None:
        raise credentials_exception
    return owner

# Middleware for language selection (simplified for example)
@app.middleware("http")
async def add_language_middleware(request: Request, call_next):
    # Check for 'lang' query parameter first
    lang = request.query_params.get("lang")
    if lang not in ['en', 'ar', 'fr']:
        # Fallback to cookie
        lang = request.cookies.get("lang")
    if lang not in ['en', 'ar', 'fr']:
        # Fallback to Accept-Language header (simplified)
        accept_language = request.headers.get("Accept-Language", "en")
        if "ar" in accept_language:
            lang = "ar"
        elif "fr" in accept_language:
            lang = "fr"
        else:
            lang = "en" # Default to English

    request.state.lang = lang
    request.state.jinja_env = get_jinja_env(lang) # Get a language-specific Jinja2 environment

    response = await call_next(request)
    response.set_cookie(key="lang", value=lang, httponly=True) # Set cookie for persistence
    return response

# Helper function to render templates
def render_template(request: Request, template_name: str, context: dict):
    template = request.state.jinja_env.get_template(template_name)
    return Response(template.render({"request": request, "lang": request.state.lang, **context}), media_type="text/html")

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.post("/signup", response_model=schemas.Token)
def signup(owner: schemas.OwnerCreate, db: Session = Depends(get_db)):
    db_owner = crud.get_owner_by_email(db, email=owner.email)
    if db_owner:
        raise HTTPException(status_code=400, detail="Email already registered")
    db_owner = crud.get_owner_by_slug(db, slug=owner.slug)
    if db_owner:
        raise HTTPException(status_code=400, detail="Business slug already taken")
    
    # Initialize services and availability as empty JSON strings
    owner_data_dict = owner.dict()
    owner_data_dict["services_json"] = "[]"
    owner_data_dict["availability_json"] = "{}"

    db_owner = crud.create_owner(db, owner)
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": db_owner.email}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/token", response_model=schemas.Token)
def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
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

@app.get("/dashboard", response_class=Response)
async def read_dashboard(request: Request, db: Session = Depends(get_db), current_owner: models.Owner = Depends(get_current_owner)):
    bookings = crud.get_owner_bookings(db, owner_id=current_owner.id)
    
    # Parse services and availability from JSON
    try:
        services = json.loads(current_owner.services_json) if current_owner.services_json else []
    except json.JSONDecodeError:
        services = []
        logger.error(f"Error decoding services_json for owner {current_owner.id}")

    try:
        availability = json.loads(current_owner.availability_json) if current_owner.availability_json else {}
    except json.JSONDecodeError:
        availability = {}
        logger.error(f"Error decoding availability_json for owner {current_owner.id}")

    context = {
        "owner": current_owner,
        "bookings": bookings,
        "services": services,
        "availability": availability
    }
    return render_template(request, "dashboard.html", context)

@app.post("/profile/update", response_model=schemas.Owner)
async def update_profile(
    owner_update: schemas.OwnerProfileUpdate,
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(get_current_owner)
):
    # Validate services
    if not isinstance(owner_update.services, list):
        raise HTTPException(status_code=400, detail="Services must be a list")
    for service in owner_update.services:
        if not isinstance(service, dict) or not all(k in service for k in ["name", "duration", "price"]):
            raise HTTPException(status_code=400, detail="Each service must have name, duration, and price")
    
    # Validate availability
    if not isinstance(owner_update.availability, dict):
        raise HTTPException(status_code=400, detail="Availability must be a dictionary")
    for day, slots in owner_update.availability.items():
        if not isinstance(slots, list):
            raise HTTPException(status_code=400, detail=f"Availability for {day} must be a list of slots")
        for slot in slots:
            if not isinstance(slot, dict) or not all(k in slot for k in ["start_time", "end_time"]):
                raise HTTPException(status_code=400, detail=f"Each slot for {day} must have start_time and end_time")
            # Basic time format validation (e.g., HH:MM)
            try:
                datetime.strptime(slot["start_time"], "%H:%M")
                datetime.strptime(slot["end_time"], "%H:%M")
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid time format for slot in {day}. Use HH:MM.")

    current_owner.services_json = json.dumps([s.dict() for s in owner_update.services])
    current_owner.availability_json = json.dumps(owner_update.availability)

    db_owner = crud.update_owner_profile(db, current_owner, owner_update)
    return db_owner

@app.get("/bookslot.app/{owner_slug}", response_class=Response)
async def public_booking_page(request: Request, owner_slug: str, db: Session = Depends(get_db)):
    owner = crud.get_owner_by_slug(db, slug=owner_slug)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Owner not found")

    try:
        services = json.loads(owner.services_json) if owner.services_json else []
        availability_data = json.loads(owner.availability_json) if owner.availability_json else {}
    except json.JSONDecodeError:
        services = []
        availability_data = {}
        logger.error(f"Error decoding services/availability JSON for owner {owner.id}")

    # Generate available slots for the next 7 days (example logic)
    available_slots = {}
    today = date.today()
    for i in range(7):
        current_date = today + timedelta(days=i)
        day_of_week = current_date.strftime("%A") # e.g., "Monday"
        
        day_slots = []
        if day_of_week in availability_data:
            for slot_range in availability_data[day_of_week]:
                start_time_str = slot_range["start_time"]
                end_time_str = slot_range["end_time"]
                
                # Convert to datetime objects for comparison
                start_dt = datetime.strptime(f"{current_date} {start_time_str}", "%Y-%m-%d %H:%M")
                end_dt = datetime.strptime(f"{current_date} {end_time_str}", "%Y-%m-%d %H:%M")

                # Assume 30-minute slots for simplicity
                current_slot_dt = start_dt
                while current_slot_dt + timedelta(minutes=30) <= end_dt:
                    day_slots.append(current_slot_dt.strftime("%H:%M"))
                    current_slot_dt += timedelta(minutes=30)
        
        available_slots[current_date.strftime("%Y-%m-%d")] = day_slots

    context = {
        "owner": owner,
        "services": services,
        "available_slots": available_slots,
        "error_message": request.query_params.get("error_message"), # For displaying form errors
        "success_message": request.query_params.get("success_message")
    }
    return render_template(request, "booking_page.html", context)

@app.post("/bookslot.app/{owner_slug}/submit")
async def submit_booking(
    request: Request,
    owner_slug: str,
    customer_name: str = Form(...),
    customer_email: EmailStr = Form(...),
    customer_phone: Optional[str] = Form(None),
    service_name: str = Form(...),
    booking_date: date = Form(...),
    booking_time: str = Form(...),
    db: Session = Depends(get_db)
):
    owner = crud.get_owner_by_slug(db, slug=owner_slug)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Owner not found")

    # Basic validation (more robust validation would check actual availability)
    if not customer_name or not customer_email or not service_name or not booking_date or not booking_time:
        return Response(status_code=status.HTTP_400_BAD_REQUEST, content="Missing form data", media_type="text/plain")

    booking_data = schemas.BookingCreate(
        customer_name=customer_name,
        customer_email=customer_email,
        customer_phone=customer_phone,
        service_name=service_name,
        booking_date=booking_date,
        booking_time=booking_time
    )

    db_booking = crud.create_booking(db, booking_data, owner.id)

    # Send notifications
    owner_email_content = notifications.get_owner_new_booking_email_content(
        owner_name=owner.name,
        customer_name=customer_name,
        customer_email=customer_email,
        customer_phone=customer_phone,
        service_name=service_name,
        booking_date=str(booking_date),
        booking_time=booking_time
    )
    notifications.send_email(owner.email, "New Booking Received!", owner_email_content)
    
    customer_email_content = notifications.get_booking_confirmation_email_content(
        owner_name=owner.name,
        customer_name=customer_name,
        service_name=service_name,
        booking_date=str(booking_date),
        booking_time=booking_time,
        owner_phone=owner.phone,
        customer_phone=customer_phone,
        owner_email=owner.email
    )
    notifications.send_email(customer_email, "Your Booking is Confirmed!", customer_email_content)

    if owner.phone:
        owner_whatsapp_content = notifications.get_owner_new_booking_whatsapp_content(
            owner_name=owner.name,
            customer_name=customer_name,
            customer_email=customer_email,
            customer_phone=customer_phone,
            service_name=service_name,
            booking_date=str(booking_date),
            booking_time=booking_time
        )
        notifications.send_whatsapp_message(owner.phone, owner_whatsapp_content)

    # Redirect to a success page or back to the booking page with a success message
    return Response(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": f"/bookslot.app/{owner_slug}?success_message=Booking confirmed!"})

# Placeholder routes for login/signup pages
@app.get("/login", response_class=Response)
async def login_page(request: Request):
    return render_template(request, "login.html", {})

@app.get("/signup", response_class=Response)
async def signup_page(request: Request):
    return render_template(request, "signup.html", {})

@app.get("/", response_class=Response)
async def home_page(request: Request):
    # Simple home page, could redirect to login or show marketing
    return render_template(request, "home.html", {})
