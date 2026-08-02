from fastapi import FastAPI, Depends, HTTPException, Request, Response, Form, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import datetime, date, time, timedelta
from typing import List, Dict, Any, Optional
import json
import logging
from jinja2 import Environment

from . import models, schemas, crud, security, notifications
from .database import engine, get_db, create_tables
from .config import settings
from .i18n_config import get_jinja_env
from starlette.middleware.sessions import SessionMiddleware

# Initialize FastAPI app
app = FastAPI()

# Add SessionMiddleware for language handling
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

# Initialize database tables
@app.on_event("startup")
def on_startup():
    create_tables()

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Dependency to get Jinja2 environment with current locale
def get_jinja_env_with_locale(request: Request):
    locale = request.session.get("locale", "en")
    return get_jinja_env(locale)

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.post("/owner/signup", response_model=schemas.Token)
def create_owner_signup(owner: schemas.OwnerCreate, db: Session = Depends(get_db)):
    db_owner = crud.get_owner_by_email(db, email=owner.email)
    if db_owner:
        raise HTTPException(status_code=400, detail="Email already registered")
    db_owner_slug = crud.get_owner_by_slug(db, slug=owner.slug)
    if db_owner_slug:
        raise HTTPException(status_code=400, detail="Business slug already taken")
    
    owner_data = owner.dict()
    # Default services and availability if not provided
    if "services" not in owner_data or not owner_data["services"]:
        owner_data["services"] = [schemas.Service(name="Default Service", duration_minutes=60, price=50.0)]
    if "availability" not in owner_data or not owner_data["availability"]:
        owner_data["availability"] = {
            "monday": [{"start": "09:00", "end": "17:00"}],
            "tuesday": [{"start": "09:00", "end": "17:00"}],
            "wednesday": [{"start": "09:00", "end": "17:00"}],
            "thursday": [{"start": "09:00", "end": "17:00"}],
            "friday": [{"start": "09:00", "end": "17:00"}],
        }

    db_owner = crud.create_owner(db=db, owner=schemas.OwnerCreate(**owner_data))
    access_token = security.create_access_token(
        data={"sub": db_owner.email}
    )
    return {"access_token": access_token, "token_type": "bearer", "owner": schemas.Owner.from_orm(db_owner)}

@app.post("/token", response_model=schemas.Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    owner = crud.authenticate_owner(db, form_data.username, form_data.password)
    if not owner:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = security.create_access_token(
        data={"sub": owner.email}
    )
    return {"access_token": access_token, "token_type": "bearer", "owner": schemas.Owner.from_orm(owner)}

@app.get("/owner/dashboard", response_class=HTMLResponse)
async def owner_dashboard(request: Request, db: Session = Depends(get_db), current_owner: models.Owner = Depends(security.get_current_owner), jinja_env: Environment = Depends(get_jinja_env_with_locale)):
    bookings = crud.get_owner_bookings(db, current_owner.id)
    template = jinja_env.get_template("dashboard.html")
    return template.render(request=request, owner=current_owner, bookings=bookings, current_locale=request.session.get("locale", "en"))

@app.get("/book/{slug}", response_class=HTMLResponse)
async def booking_page(request: Request, slug: str, db: Session = Depends(get_db), jinja_env: Environment = Depends(get_jinja_env_with_locale)):
    owner = crud.get_owner_by_slug(db, slug=slug)
    if not owner:
        raise HTTPException(status_code=404, detail="Booking page not found")
    
    # Parse services and availability
    services = json.loads(owner.services_json) if owner.services_json else []
    availability = json.loads(owner.availability_json) if owner.availability_json else {}

    # Logic to generate available time slots for the next 7 days
    available_slots = {}
    today = date.today()
    for i in range(7):
        current_date = today + timedelta(days=i)
        day_name = current_date.strftime('%A').lower() # e.g., "monday"
        
        if day_name in availability:
            slots_for_day = []
            for slot_range in availability[day_name]:
                start_time = datetime.strptime(slot_range['start'], '%H:%M').time()
                end_time = datetime.strptime(slot_range['end'], '%H:%M').time()
                
                # Assume a default service duration for slot generation (e.g., 30 minutes)
                # In a real app, this would depend on selected service
                slot_duration_minutes = 30 
                
                current_slot_start = datetime.combine(current_date, start_time)
                while current_slot_start + timedelta(minutes=slot_duration_minutes) <= datetime.combine(current_date, end_time):
                    slots_for_day.append(current_slot_start.strftime('%H:%M'))
                    current_slot_start += timedelta(minutes=slot_duration_minutes)
            
            available_slots[current_date.isoformat()] = slots_for_day

    template = jinja_env.get_template("booking_page.html")
    return template.render(
        request=request,
        owner=owner,
        services=services,
        available_slots=available_slots,
        current_locale=request.session.get("locale", "en")
    )

@app.post("/book/{slug}", response_class=HTMLResponse)
async def submit_booking(
    request: Request,
    slug: str,
    db: Session = Depends(get_db),
    customer_name: str = Form(...),
    customer_email: str = Form(...),
    customer_phone: str = Form(...),
    service_name: str = Form(...),
    booking_date_str: str = Form(...),
    booking_time_str: str = Form(...),
    jinja_env: Environment = Depends(get_jinja_env_with_locale)
):
    owner = crud.get_owner_by_slug(db, slug=slug)
    if not owner:
        raise HTTPException(status_code=404, detail="Booking page not found")

    try:
        booking_date = date.fromisoformat(booking_date_str)
        booking_time = time.fromisoformat(booking_time_str)
        booking_datetime = datetime.combine(booking_date, booking_time)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date or time format.")

    # Basic validation (more robust validation would check against owner's availability)
    if booking_datetime < datetime.now():
        raise HTTPException(status_code=400, detail="Cannot book in the past.")

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
        db_booking = crud.create_booking(db, booking_data, owner.id)
        # Send notifications
        notifications.send_booking_confirmation_email(
            owner_email=owner.email,
            customer_email=customer_email,
            booking_details=db_booking,
            owner_name=owner.name,
            business_name=owner.business_name
        )
        notifications.send_whatsapp_notification(
            owner_phone=owner.phone,
            customer_name=customer_name,
            service_name=service_name,
            booking_date=booking_date.isoformat(),
            booking_time=booking_time.isoformat()
        )

        template = jinja_env.get_template("booking_confirmation.html")
        return template.render(request=request, booking=db_booking, owner=owner, current_locale=request.session.get("locale", "en"))
    except Exception as e:
        logger.error(f"Error during booking submission or notification: {e}")
        raise HTTPException(status_code=500, detail="Failed to process booking.")

@app.put("/owner/profile", response_model=schemas.Owner, dependencies=[Depends(security.get_current_owner)])
async def update_owner_profile_endpoint(
    owner_update: schemas.OwnerProfileUpdate,
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(security.get_current_owner)
):
    try:
        updated_owner = crud.update_owner_profile(db, current_owner, owner_update)
        return updated_owner
    except Exception as e:
        logger.error(f"Error updating owner profile: {e}")
        raise HTTPException(status_code=500, detail="Failed to update profile.")

@app.get("/set_language/{lang}")
async def set_language(request: Request, lang: str):
    if lang in ["en", "ar", "fr"]:
        request.session["locale"] = lang
    
    # Redirect back to the previous page or a default page
    referer = request.headers.get("referer")
    if referer:
        return RedirectResponse(url=referer, status_code=status.HTTP_302_FOUND)
    return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)