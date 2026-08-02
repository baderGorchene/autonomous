from fastapi import FastAPI, Depends, HTTPException, status, Request, Form, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from datetime import date, datetime, timedelta
import json
import logging
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import JSONResponse
from starlette.datastructures import URL
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

from . import crud, models, schemas, security, notifications
from .database import SessionLocal, engine, create_tables, get_db
from .config import settings
from .i18n_config import get_jinja_env

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

# Create database tables on startup
@app.on_event("startup")
def on_startup():
    create_tables()

# Dependency for Jinja2 environment
def get_templates(request: Request):
    locale = request.session.get("locale", "en")
    return get_jinja_env(locale=locale)

@app.middleware("http")
async def add_locale_to_request(request: Request, call_next):
    # Set default locale if not present in session
    if "locale" not in request.session:
        request.session["locale"] = "en"
    
    # Allow locale to be overridden by query parameter
    if "lang" in request.query_params:
        request.session["locale"] = request.query_params["lang"]
        # Redirect to clean URL without lang param to avoid persistence issues
        parsed_url = urlparse(str(request.url))
        query_params = parse_qs(parsed_url.query)
        if "lang" in query_params:
            del query_params["lang"]
        new_query = urlencode(query_params, doseq=True)
        new_url = urlunparse(parsed_url._replace(query=new_query))
        response = RedirectResponse(url=new_url, status_code=status.HTTP_302_FOUND)
        response.set_cookie(key="locale", value=request.session["locale"])
        return response

    # Also check cookie if session is not yet established (e.g., first visit)
    if "locale" not in request.session and "locale" in request.cookies:
        request.session["locale"] = request.cookies["locale"]

    request.state.locale = request.session["locale"]
    response = await call_next(request)
    response.set_cookie(key="locale", value=request.session["locale"])
    return response

# Helper to get current owner from session
def get_current_owner_from_session(request: Request, db: Session = Depends(get_db)):
    owner_id = request.session.get("owner_id")
    if owner_id:
        owner = crud.get_owner(db, owner_id=owner_id)
        if owner:
            return owner
    return None

# Root endpoint - redirect to login or dashboard
@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request, db: Session = Depends(get_db)):
    owner = get_current_owner_from_session(request, db)
    if owner:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

# Login page
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, templates: Jinja2Templates = Depends(get_templates)):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login", response_class=HTMLResponse)
async def login(request: Request, response: Response, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db), templates: Jinja2Templates = Depends(get_templates)):
    owner = crud.authenticate_owner(db, email, password)
    if not owner:
        return templates.TemplateResponse("login.html", {"request": request, "error": templates.get_translator().gettext("Incorrect email or password")})
    
    request.session["owner_id"] = owner.id
    request.session["owner_email"] = owner.email
    
    return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)

# Signup page
@app.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request, templates: Jinja2Templates = Depends(get_templates)):
    return templates.TemplateResponse("signup.html", {"request": request})

@app.post("/signup", response_class=HTMLResponse)
async def signup(
    request: Request, 
    name: str = Form(...), 
    email: str = Form(...), 
    password: str = Form(...), 
    business_name: str = Form(...), 
    slug: str = Form(...),
    phone: Optional[str] = Form(None),
    db: Session = Depends(get_db), 
    templates: Jinja2Templates = Depends(get_templates)
):
    owner = crud.get_owner_by_email(db, email=email)
    if owner:
        return templates.TemplateResponse("signup.html", {"request": request, "error": templates.get_translator().gettext("Email already registered")})
    
    owner_by_slug = crud.get_owner_by_slug(db, slug=slug)
    if owner_by_slug:
        return templates.TemplateResponse("signup.html", {"request": request, "error": templates.get_translator().gettext("Custom URL already taken")})

    try:
        owner_in = schemas.OwnerCreate(name=name, email=email, password=password, business_name=business_name, slug=slug, phone=phone)
        db_owner = crud.create_owner(db=db, owner=owner_in)
        
        request.session["owner_id"] = db_owner.id
        request.session["owner_email"] = db_owner.email
        
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    except Exception as e:
        logger.error(f"Signup error: {e}")
        return templates.TemplateResponse("signup.html", {"request": request, "error": templates.get_translator().gettext("An error occurred during signup. Please try again.")})

# Logout
@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

# Dashboard
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db), templates: Jinja2Templates = Depends(get_templates)):
    owner = get_current_owner_from_session(request, db)
    if not owner:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    
    owner_bookings = crud.get_owner_bookings(db, owner_id=owner.id)
    
    # Filter for upcoming bookings (today and future)
    today = datetime.now().date()
    upcoming_bookings = [
        booking for booking in owner_bookings 
        if booking.booking_date.date() >= today
    ]
    
    # Sort by date and time
    upcoming_bookings.sort(key=lambda b: (b.booking_date, b.booking_time))

    # Parse services and availability JSON
    services = json.loads(owner.services_json) if owner.services_json else []
    availability = json.loads(owner.availability_json) if owner.availability_json else {}

    return templates.TemplateResponse("dashboard.html", {
        "request": request, 
        "owner": owner, 
        "upcoming_bookings": upcoming_bookings,
        "services": services,
        "availability": availability
    })

# Profile update
@app.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request, db: Session = Depends(get_db), templates: Jinja2Templates = Depends(get_templates)):
    owner = get_current_owner_from_session(request, db)
    if not owner:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    
    return templates.TemplateResponse("profile.html", {"request": request, "owner": owner})

@app.post("/profile", response_class=HTMLResponse)
async def update_profile(
    request: Request,
    name: str = Form(...),
    business_name: str = Form(...),
    phone: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    templates: Jinja2Templates = Depends(get_templates)
):
    owner = get_current_owner_from_session(request, db)
    if not owner:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    
    try:
        owner_update = schemas.OwnerProfileUpdate(name=name, business_name=business_name, phone=phone)
        updated_owner = crud.update_owner_profile(db, current_owner=owner, owner_update=owner_update)
        return templates.TemplateResponse("profile.html", {"request": request, "owner": updated_owner, "message": templates.get_translator().gettext("Profile updated successfully!")})
    except Exception as e:
        logger.error(f"Profile update error: {e}")
        return templates.TemplateResponse("profile.html", {"request": request, "owner": owner, "error": templates.get_translator().gettext("An error occurred during profile update. Please try again.")})

# Service and Availability Setup
@app.get("/setup-services", response_class=HTMLResponse)
async def setup_services_page(request: Request, db: Session = Depends(get_db), templates: Jinja2Templates = Depends(get_templates)):
    owner = get_current_owner_from_session(request, db)
    if not owner:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    
    services = json.loads(owner.services_json) if owner.services_json else []
    availability = json.loads(owner.availability_json) if owner.availability_json else {}
    
    return templates.TemplateResponse("setup_services.html", {
        "request": request, 
        "owner": owner, 
        "services": services, 
        "availability": availability
    })

@app.post("/setup-services", response_class=HTMLResponse)
async def update_services(
    request: Request,
    services_data: str = Form(...), # JSON string
    db: Session = Depends(get_db),
    templates: Jinja2Templates = Depends(get_templates)
):
    owner = get_current_owner_from_session(request, db)
    if not owner:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    
    try:
        # Validate services_data as JSON
        parsed_services = json.loads(services_data)
        # Optional: Add Pydantic validation for each service in the list
        for service_data in parsed_services:
            schemas.ServiceCreate(**service_data) # Validate service schema
            
        owner.services_json = services_data
        db.add(owner)
        db.commit()
        db.refresh(owner)
        
        services = json.loads(owner.services_json) if owner.services_json else []
        availability = json.loads(owner.availability_json) if owner.availability_json else {}

        return templates.TemplateResponse("setup_services.html", {
            "request": request, 
            "owner": owner, 
            "services": services, 
            "availability": availability,
            "message": templates.get_translator().gettext("Services updated successfully!")
        })
    except json.JSONDecodeError:
        error_msg = templates.get_translator().gettext("Invalid JSON format for services data.")
        logger.error(f"Service update error for owner {owner.id}: {error_msg}")
        return templates.TemplateResponse("setup_services.html", {
            "request": request, 
            "owner": owner, 
            "services": json.loads(owner.services_json) if owner.services_json else [],
            "availability": json.loads(owner.availability_json) if owner.availability_json else {},
            "error": error_msg
        })
    except Exception as e:
        error_msg = templates.get_translator().gettext("An error occurred during service update. Please try again.")
        logger.error(f"Service update error for owner {owner.id}: {e}")
        return templates.TemplateResponse("setup_services.html", {
            "request": request, 
            "owner": owner, 
            "services": json.loads(owner.services_json) if owner.services_json else [],
            "availability": json.loads(owner.availability_json) if owner.availability_json else {},
            "error": error_msg
        })

@app.post("/setup-availability", response_class=HTMLResponse)
async def update_availability(
    request: Request,
    availability_data: str = Form(...), # JSON string
    db: Session = Depends(get_db),
    templates: Jinja2Templates = Depends(get_templates)
):
    owner = get_current_owner_from_session(request, db)
    if not owner:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    
    try:
        # Validate availability_data as JSON
        parsed_availability = json.loads(availability_data)
        # Optional: Add more specific validation for availability structure if needed
            
        owner.availability_json = availability_data
        db.add(owner)
        db.commit()
        db.refresh(owner)

        services = json.loads(owner.services_json) if owner.services_json else []
        availability = json.loads(owner.availability_json) if owner.availability_json else {}
        
        return templates.TemplateResponse("setup_services.html", {
            "request": request, 
            "owner": owner, 
            "services": services, 
            "availability": availability,
            "message": templates.get_translator().gettext("Availability updated successfully!")
        })
    except json.JSONDecodeError:
        error_msg = templates.get_translator().gettext("Invalid JSON format for availability data.")
        logger.error(f"Availability update error for owner {owner.id}: {error_msg}")
        return templates.TemplateResponse("setup_services.html", {
            "request": request, 
            "owner": owner, 
            "services": json.loads(owner.services_json) if owner.services_json else [],
            "availability": json.loads(owner.availability_json) if owner.availability_json else {},
            "error": error_msg
        })
    except Exception as e:
        error_msg = templates.get_translator().gettext("An error occurred during availability update. Please try again.")
        logger.error(f"Availability update error for owner {owner.id}: {e}")
        return templates.TemplateResponse("setup_services.html", {
            "request": request, 
            "owner": owner, 
            "services": json.loads(owner.services_json) if owner.services_json else [],
            "availability": json.loads(owner.availability_json) if owner.availability_json else {},
            "error": error_msg
        })

# Public booking page
@app.get("/{owner_slug}", response_class=HTMLResponse)
async def public_booking_page(owner_slug: str, request: Request, db: Session = Depends(get_db), templates: Jinja2Templates = Depends(get_templates)):
    owner = crud.get_owner_by_slug(db, slug=owner_slug)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking page not found")

    services = json.loads(owner.services_json) if owner.services_json else []
    availability = json.loads(owner.availability_json) if owner.availability_json else {}
    
    # For simplicity, let's assume availability is a dict like {"Monday": ["09:00", "10:00"], ...}
    # In a real app, this would involve more complex logic to calculate available slots based on bookings
    
    return templates.TemplateResponse("booking_page.html", {
        "request": request, 
        "owner": owner, 
        "services": services, 
        "availability": availability,
        "owner_slug": owner_slug
    })

@app.post("/{owner_slug}/book", response_class=HTMLResponse)
async def submit_booking(
    owner_slug: str,
    request: Request,
    customer_name: str = Form(...),
    customer_email: EmailStr = Form(...),
    customer_phone: Optional[str] = Form(None),
    service_name: str = Form(...),
    booking_date_str: str = Form(..., alias="booking_date"), # Renamed to avoid conflict with datetime
    booking_time: str = Form(...),
    db: Session = Depends(get_db),
    templates: Jinja2Templates = Depends(get_templates)
):
    owner = crud.get_owner_by_slug(db, slug=owner_slug)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking page not found")

    try:
        booking_date = datetime.strptime(booking_date_str, "%Y-%m-%d")
        
        booking_in = schemas.BookingCreate(
            customer_name=customer_name,
            customer_email=customer_email,
            customer_phone=customer_phone,
            service_name=service_name,
            booking_date=booking_date,
            booking_time=booking_time
        )
        
        db_booking = crud.create_booking(db=db, booking=booking_in, owner_id=owner.id)

        # Send notifications
        booking_details = booking_in.dict()
        booking_details['booking_date'] = booking_date # Ensure datetime object for notification
        notifications.send_booking_confirmation_email(
            owner_email=owner.email,
            customer_email=customer_email,
            booking_details=booking_details,
            owner_name=owner.name,
            business_name=owner.business_name
        )
        if owner.phone:
            notifications.send_owner_whatsapp_notification(
                owner_phone=owner.phone,
                booking_details=booking_details,
                business_name=owner.business_name
            )

        return templates.TemplateResponse("booking_confirmation.html", {
            "request": request, 
            "owner": owner, 
            "booking": db_booking,
            "message": templates.get_translator().gettext("Your booking has been successfully confirmed!")
        })
    except ValueError:
        error_msg = templates.get_translator().gettext("Invalid date format. Please use YYYY-MM-DD.")
        logger.error(f"Booking submission error for {owner_slug}: {error_msg}")
        services = json.loads(owner.services_json) if owner.services_json else []
        availability = json.loads(owner.availability_json) if owner.availability_json else {}
        return templates.TemplateResponse("booking_page.html", {
            "request": request, 
            "owner": owner, 
            "services": services, 
            "availability": availability,
            "owner_slug": owner_slug,
            "error": error_msg
        })
    except Exception as e:
        error_msg = templates.get_translator().gettext("An error occurred during booking. Please try again.")
        logger.error(f"Booking submission error for {owner_slug}: {e}")
        services = json.loads(owner.services_json) if owner.services_json else []
        availability = json.loads(owner.availability_json) if owner.availability_json else {}
        return templates.TemplateResponse("booking_page.html", {
            "request": request, 
            "owner": owner, 
            "services": services, 
            "availability": availability,
            "owner_slug": owner_slug,
            "error": error_msg
        })

# Health check endpoint
@app.get("/health")
def health_check():
    return {"status": "ok"}
