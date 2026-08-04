from fastapi import FastAPI, Depends, HTTPException, status, Request, Response, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import timedelta, date, datetime
import json
import os
import logging
from typing import List, Optional

from . import crud, models, schemas, security, notifications
from .database import engine, create_tables, get_db
from .dependencies import get_current_owner
from .config import settings
from .i18n_config import get_jinja_templates

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create tables on startup
models.Base.metadata.create_all(bind=engine)

app = FastAPI()

# Mount static files (CSS, JS, images, etc.)
# Assuming static files are in a 'static' directory at the project root
STATIC_DIR = os.path.join(settings.PROJECT_ROOT, 'static')
if not os.path.exists(STATIC_DIR):
    os.makedirs(STATIC_DIR)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Middleware for language detection and setting
@app.middleware("http")
async def add_i18n_middleware(request: Request, call_next):
    # Try to get language from query parameter
    lang = request.query_params.get("lang")
    if lang not in ["en", "ar", "fr"]:
        # Fallback to cookie, then Accept-Language header, then default to 'en'
        lang = request.cookies.get("lang")
        if lang not in ["en", "ar", "fr"]:
            accept_language = request.headers.get("Accept-Language", "en").split(',')[0].lower()
            if 'ar' in accept_language:
                lang = 'ar'
            elif 'fr' in accept_language:
                lang = 'fr'
            else:
                lang = 'en'
    
    request.state.lang = lang
    response = await call_next(request)
    # Set language cookie for persistence
    response.set_cookie(key="lang", value=lang, httponly=True, samesite="lax")
    return response

# Dependency to get Jinja2Templates instance with current locale
def get_templates_env(request: Request):
    return get_jinja_templates(request.state.lang)

@app.get("/health", response_class=HTMLResponse)
async def health_check():
    return "<h1>BookSlot is running!</h1>"

@app.post("/token", response_model=schemas.Token)
async def login_for_access_token(db: Session = Depends(get_db), form_data: OAuth2PasswordRequestForm = Depends()):
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

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, templates: Jinja2Templates = Depends(get_templates_env)):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login", response_class=RedirectResponse)
async def handle_login(request: Request, db: Session = Depends(get_db), email: str = Form(...), password: str = Form(...)):
    owner = crud.authenticate_owner(db, email, password)
    if not owner:
        # TODO: Add error message to template
        return RedirectResponse(url="/login?error=invalid_credentials", status_code=status.HTTP_303_SEE_OTHER)
    
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": owner.email}, expires_delta=access_token_expires
    )
    
    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(key="access_token", value=access_token, httponly=True, samesite="lax")
    return response

@app.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request, templates: Jinja2Templates = Depends(get_templates_env)):
    return templates.TemplateResponse("signup.html", {"request": request})

@app.post("/signup", response_class=RedirectResponse)
async def handle_signup(request: Request, db: Session = Depends(get_db),
                        name: str = Form(...), email: str = Form(...), password: str = Form(...),
                        business_name: str = Form(...), slug: str = Form(...), phone: Optional[str] = Form(None)):
    
    # Basic slug validation
    if not slug or not schemas.OwnerBase(name=name, email=email, business_name=business_name, slug=slug, phone=phone).model_validate({"slug": slug}):
        return RedirectResponse(url="/signup?error=invalid_slug", status_code=status.HTTP_303_SEE_OTHER)

    owner = crud.get_owner_by_email(db, email=email)
    if owner:
        return RedirectResponse(url="/signup?error=email_exists", status_code=status.HTTP_303_SEE_OTHER)
    
    owner_by_slug = crud.get_owner_by_slug(db, slug=slug)
    if owner_by_slug:
        return RedirectResponse(url="/signup?error=slug_exists", status_code=status.HTTP_303_SEE_OTHER)

    try:
        owner_create = schemas.OwnerCreate(
            name=name, email=email, password=password,
            business_name=business_name, slug=slug, phone=phone
        )
        db_owner = crud.create_owner(db=db, owner=owner_create)
        
        # Log in the new owner immediately
        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = security.create_access_token(
            data={"sub": db_owner.email}, expires_delta=access_token_expires
        )
        
        response = RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
        response.set_cookie(key="access_token", value=access_token, httponly=True, samesite="lax")
        return response
    except Exception as e:
        logger.error(f"Error during signup: {e}")
        return RedirectResponse(url="/signup?error=generic_error", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request, templates: Jinja2Templates = Depends(get_templates_env),
                         current_owner: schemas.Owner = Depends(get_current_owner),
                         db: Session = Depends(get_db)):
    
    bookings = crud.get_owner_bookings(db, current_owner.id)
    # Parse services and availability from JSON strings
    services = json.loads(current_owner.services_json) if current_owner.services_json else []
    availability = json.loads(current_owner.availability_json) if current_owner.availability_json else {}

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "owner": current_owner,
        "bookings": bookings,
        "services": services,
        "availability": availability,
        "booking_page_url": f"/book/{current_owner.slug}"
    })

@app.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request, templates: Jinja2Templates = Depends(get_templates_env),
                       current_owner: schemas.Owner = Depends(get_current_owner)):
    
    services = json.loads(current_owner.services_json) if current_owner.services_json else []
    availability = json.loads(current_owner.availability_json) if current_owner.availability_json else {}

    return templates.TemplateResponse("profile.html", {
        "request": request,
        "owner": current_owner,
        "services": services,
        "availability": availability
    })

@app.post("/profile", response_class=RedirectResponse)
async def update_profile(request: Request, db: Session = Depends(get_db),
                         current_owner: schemas.Owner = Depends(get_current_owner),
                         name: str = Form(...), business_name: str = Form(...), phone: Optional[str] = Form(None)):
    try:
        owner_update = schemas.OwnerProfileUpdate(name=name, business_name=business_name, phone=phone)
        crud.update_owner_profile(db, current_owner, owner_update)
        # TODO: Add success message
        return RedirectResponse(url="/dashboard?message=profile_updated", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        logger.error(f"Error updating profile for owner {current_owner.id}: {e}")
        return RedirectResponse(url="/profile?error=update_failed", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/book/{owner_slug}", response_class=HTMLResponse)
async def public_booking_page(request: Request, owner_slug: str, templates: Jinja2Templates = Depends(get_templates_env), db: Session = Depends(get_db)):
    owner = crud.get_owner_by_slug(db, slug=owner_slug)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking page not found")

    services = json.loads(owner.services_json) if owner.services_json else []
    availability = json.loads(owner.availability_json) if owner.availability_json else {}

    # Example services and availability if not set (for testing/initial setup)
    if not services:
        services = [
            {"name": "Haircut", "duration_minutes": 30, "price": 25.00},
            {"name": "Manicure", "duration_minutes": 60, "price": 40.00}
        ]
    
    # Generate available slots for the next 7 days (simplified for MVP)
    available_slots = {}
    today = date.today()
    for i in range(7):
        current_date = today + timedelta(days=i)
        day_of_week = current_date.weekday() # Monday 0, Sunday 6
        
        day_availability = next((av for av in availability.get("weekly_availability", []) if av["day_of_week"] == day_of_week), None)
        
        if day_availability:
            start_time_str = day_availability["start_time"]
            end_time_str = day_availability["end_time"]
            
            # Simple slot generation (e.g., every 30 mins)
            slots_for_day = []
            start_dt = datetime.strptime(start_time_str, "%H:%M").time()
            end_dt = datetime.strptime(end_time_str, "%H:%M").time()
            
            current_slot_dt = datetime.combine(current_date, start_dt)
            while current_slot_dt.time() < end_dt:
                slot_end_dt = current_slot_dt + timedelta(minutes=30) # Assuming 30 min slots for simplicity
                if slot_end_dt.time() <= end_dt:
                    slots_for_day.append(f"{current_slot_dt.strftime('%H:%M')}-{slot_end_dt.strftime('%H:%M')}")
                current_slot_dt = slot_end_dt
            available_slots[current_date.isoformat()] = slots_for_day
        else:
            available_slots[current_date.isoformat()] = [] # No availability for this day

    return templates.TemplateResponse("booking_page.html", {
        "request": request,
        "owner": owner,
        "services": services,
        "available_slots": available_slots,
        "current_date": today.isoformat()
    })

@app.post("/book/{owner_slug}", response_class=HTMLResponse)
async def submit_booking(request: Request, owner_slug: str, templates: Jinja2Templates = Depends(get_templates_env),
                         db: Session = Depends(get_db),
                         customer_name: str = Form(...), customer_email: EmailStr = Form(...),
                         customer_phone: Optional[str] = Form(None),
                         service_name: str = Form(...), booking_date: str = Form(...), booking_time: str = Form(...)):
    
    owner = crud.get_owner_by_slug(db, slug=owner_slug)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking page not found")

    try:
        booking_date_obj = datetime.strptime(booking_date, "%Y-%m-%d").date()
        booking_create = schemas.BookingCreate(
            customer_name=customer_name,
            customer_email=customer_email,
            customer_phone=customer_phone,
            service_name=service_name,
            booking_date=booking_date_obj,
            booking_time=booking_time
        )
        new_booking = crud.create_booking(db, booking_create, owner.id)

        booking_details = {
            "owner_name": owner.name,
            "owner_email": owner.email,
            "owner_phone": owner.phone,
            "customer_name": new_booking.customer_name,
            "customer_email": new_booking.customer_email,
            "customer_phone": new_booking.customer_phone,
            "service_name": new_booking.service_name,
            "booking_date": new_booking.booking_date.strftime("%Y-%m-%d"),
            "booking_time": new_booking.booking_time,
        }
        
        # Send notifications
        notifications.send_booking_notification(
            owner_email=owner.email,
            owner_phone=owner.phone,
            customer_email=new_booking.customer_email,
            customer_phone=new_booking.customer_phone,
            booking_details=booking_details,
            is_owner_notification=True
        )
        notifications.send_booking_notification(
            owner_email=owner.email, # Not used for customer notification
            owner_phone=owner.phone, # Not used for customer notification
            customer_email=new_booking.customer_email,
            customer_phone=new_booking.customer_phone,
            booking_details=booking_details,
            is_owner_notification=False
        )

        return templates.TemplateResponse("booking_confirmation.html", {
            "request": request,
            "booking": new_booking,
            "owner": owner
        })
    except Exception as e:
        logger.error(f"Error submitting booking for {owner_slug}: {e}")
        # TODO: Better error handling and display for the user
        return templates.TemplateResponse("booking_page.html", {
            "request": request,
            "owner": owner,
            "services": json.loads(owner.services_json) if owner.services_json else [], # Re-render with existing data
            "error_message": "Failed to process booking. Please try again."
        }, status_code=status.HTTP_400_BAD_REQUEST)