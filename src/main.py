from fastapi import FastAPI, Depends, HTTPException, status, Request, Response, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta, date, datetime
from typing import List, Dict, Any, Optional
import json
import logging
import os
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

from . import crud, models, schemas, security, notifications
from .database import SessionLocal, engine, create_tables, get_db
from .config import settings
from .i18n_config import get_jinja_env # Import the configured Jinja2 environment

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create tables on startup if not in testing mode
if not settings.TESTING:
    create_tables()

app = FastAPI()

# OAuth2PasswordBearer for token authentication
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/token")

# Dependency to get current owner from token
async def get_current_owner(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = security.decode_access_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    email: str = payload.get("sub")
    if email is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    owner = crud.get_owner_by_email(db, email=email)
    if owner is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Owner not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return owner

# Helper to get Jinja2 environment with correct locale
def get_template_env(request: Request):
    locale = request.cookies.get("lang", "en")
    return get_jinja_env(locale)

@app.get("/health", response_class=HTMLResponse)
async def health_check():
    return "OK"

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    env = get_template_env(request)
    template = env.get_template("index.html") # Assuming an index.html for landing/redirect
    return template.render({"request": request})

# --- Authentication and Owner Management ---
@app.get("/signup", response_class=HTMLResponse)
async def signup_form(request: Request):
    env = get_template_env(request)
    template = env.get_template("signup.html")
    return template.render({"request": request})

@app.post("/signup", response_class=HTMLResponse)
async def signup(
    request: Request,
    response: Response,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    business_name: str = Form(...),
    slug: str = Form(...),
    phone: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    env = get_template_env(request)
    template = env.get_template("signup.html")
    db_owner = crud.get_owner_by_email(db, email=email)
    if db_owner:
        return template.render({"request": request, "error": env.gettext("Email already registered")})
    
    db_owner_slug = crud.get_owner_by_slug(db, slug=slug)
    if db_owner_slug:
        return template.render({"request": request, "error": env.gettext("Booking page URL (slug) already taken")})

    try:
        owner_in = schemas.OwnerCreate(name=name, email=email, password=password, business_name=business_name, slug=slug, phone=phone)
        owner = crud.create_owner(db=db, owner=owner_in)
        
        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = security.create_access_token(
            data={"sub": owner.email}, expires_delta=access_token_expires
        )
        response = RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
        response.set_cookie(key="access_token", value=access_token, httponly=True, expires=access_token_expires.total_seconds())
        return response
    except Exception as e:
        logger.error(f"Signup error: {e}")
        return template.render({"request": request, "error": env.gettext("An error occurred during signup.")})

@app.get("/login", response_class=HTMLResponse)
async def login_form(request: Request):
    env = get_template_env(request)
    template = env.get_template("login.html")
    return template.render({"request": request})

@app.post("/login", response_class=HTMLResponse)
async def login(
    request: Request,
    response: Response,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    env = get_template_env(request)
    template = env.get_template("login.html")
    owner = crud.authenticate_owner(db, email, password)
    if not owner:
        return template.render({"request": request, "error": env.gettext("Incorrect email or password")})
    
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": owner.email}, expires_delta=access_token_expires
    )
    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    response.set_cookie(key="access_token", value=access_token, httponly=True, expires=access_token_expires.total_seconds())
    return response

@app.post("/logout", response_class=RedirectResponse)
async def logout(response: Response):
    response = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    response.delete_cookie(key="access_token")
    return response

# --- Owner Dashboard ---
@app.get("/dashboard", response_class=HTMLResponse)
async def owner_dashboard(request: Request, db: Session = Depends(get_db), current_owner: models.Owner = Depends(get_current_owner)):
    env = get_template_env(request)
    template = env.get_template("dashboard.html")
    
    owner_bookings = crud.get_owner_bookings(db, owner_id=current_owner.id)
    
    # Filter for upcoming bookings (today or in the future)
    today = datetime.now().date()
    upcoming_bookings = [
        b for b in owner_bookings 
        if b.booking_date.date() >= today
    ]
    
    # Sort bookings by date and time
    upcoming_bookings.sort(key=lambda x: (x.booking_date, x.booking_time))

    # Parse services and availability for display
    services = json.loads(current_owner.services_json) if current_owner.services_json else []
    availability = json.loads(current_owner.availability_json) if current_owner.availability_json else {}

    return template.render({
        "request": request,
        "owner": current_owner,
        "upcoming_bookings": upcoming_bookings,
        "services": services,
        "availability": availability
    })

@app.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request, current_owner: models.Owner = Depends(get_current_owner)):
    env = get_template_env(request)
    template = env.get_template("profile.html")
    
    services = json.loads(current_owner.services_json) if current_owner.services_json else []
    availability = json.loads(current_owner.availability_json) if current_owner.availability_json else {}

    return template.render({
        "request": request,
        "owner": current_owner,
        "services": services,
        "availability": availability,
        "days_of_week": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    })

@app.post("/profile", response_class=HTMLResponse)
async def update_profile(
    request: Request,
    response: Response,
    name: str = Form(...),
    business_name: str = Form(...),
    phone: Optional[str] = Form(None),
    services_json: str = Form("[]"), # Expecting JSON string from hidden input
    availability_json: str = Form("{}", alias="availability"), # Expecting JSON string from hidden input
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(get_current_owner)
):
    env = get_template_env(request)
    template = env.get_template("profile.html")
    
    try:
        # Validate services_json
        parsed_services = json.loads(services_json)
        validated_services = [schemas.ServiceCreate(**s) for s in parsed_services]
        
        # Validate availability_json
        parsed_availability = json.loads(availability_json)
        validated_availability = {}
        for day, slots in parsed_availability.items():
            validated_availability[day] = [schemas.AvailabilitySlot(**s) for s in slots]

        owner_update_schema = schemas.OwnerProfileUpdate(
            name=name,
            business_name=business_name,
            phone=phone,
            services=validated_services,
            availability=validated_availability
        )
        
        updated_owner = crud.update_owner_profile(db, current_owner, owner_update_schema)
        updated_owner.services_json = json.dumps([s.dict() for s in validated_services])
        updated_owner.availability_json = json.dumps({
            day: [slot.dict() for slot in slots]
            for day, slots in validated_availability.items()
        })
        db.add(updated_owner)
        db.commit()
        db.refresh(updated_owner)

        return template.render({
            "request": request,
            "owner": updated_owner,
            "services": json.loads(updated_owner.services_json),
            "availability": json.loads(updated_owner.availability_json),
            "days_of_week": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
            "message": env.gettext("Profile updated successfully!")
        })
    except json.JSONDecodeError:
        return template.render({
            "request": request,
            "owner": current_owner,
            "services": json.loads(current_owner.services_json) if current_owner.services_json else [],
            "availability": json.loads(current_owner.availability_json) if current_owner.availability_json else {},
            "days_of_week": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
            "error": env.gettext("Invalid JSON format for services or availability.")
        })
    except Exception as e:
        logger.error(f"Error updating profile for owner {current_owner.id}: {e}")
        return template.render({
            "request": request,
            "owner": current_owner,
            "services": json.loads(current_owner.services_json) if current_owner.services_json else [],
            "availability": json.loads(current_owner.availability_json) if current_owner.availability_json else {},
            "days_of_week": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
            "error": env.gettext(f"An error occurred: {e}")
        })

# --- Public Booking Page ---
@app.get("/book/{owner_slug}", response_class=HTMLResponse)
async def public_booking_page(request: Request, owner_slug: str, db: Session = Depends(get_db)):
    env = get_template_env(request)
    template = env.get_template("booking_page.html")
    owner = crud.get_owner_by_slug(db, slug=owner_slug)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=env.gettext("Booking page not found"))
    
    services = json.loads(owner.services_json) if owner.services_json else []
    availability = json.loads(owner.availability_json) if owner.availability_json else {}

    return template.render({
        "request": request,
        "owner": owner,
        "services": services,
        "availability": availability
    })

@app.post("/book/{owner_slug}", response_class=HTMLResponse)
async def submit_booking(
    request: Request,
    owner_slug: str,
    customer_name: str = Form(...),
    customer_email: EmailStr = Form(...),
    customer_phone: Optional[str] = Form(None),
    service_name: str = Form(...),
    booking_date_str: str = Form(..., alias="booking_date"), # Expecting YYYY-MM-DD
    booking_time: str = Form(...), # e.g., "10:00 AM"
    db: Session = Depends(get_db)
):
    env = get_template_env(request)
    owner = crud.get_owner_by_slug(db, slug=owner_slug)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=env.gettext("Booking page not found"))

    try:
        # Validate date format
        booking_date = datetime.strptime(booking_date_str, "%Y-%m-%d").date()
        
        # Check if the requested slot is available (simplified check)
        # This is a basic check. A robust system would check against existing bookings too.
        day_of_week = booking_date.strftime("%A")
        owner_availability = json.loads(owner.availability_json).get(day_of_week, [])
        
        is_available = False
        for slot in owner_availability:
            slot_start = datetime.strptime(slot["start_time"], "%H:%M").time()
            slot_end = datetime.strptime(slot["end_time"], "%H:%M").time()
            requested_time_obj = datetime.strptime(booking_time, "%I:%M %p").time() # e.g., "10:00 AM"
            
            if slot_start <= requested_time_obj < slot_end:
                is_available = True
                break
        
        if not is_available:
            return env.get_template("booking_page.html").render({
                "request": request,
                "owner": owner,
                "services": json.loads(owner.services_json),
                "availability": json.loads(owner.availability_json),
                "error": env.gettext("The selected time slot is not available.")
            })

        booking_in = schemas.BookingCreate(
            customer_name=customer_name,
            customer_email=customer_email,
            customer_phone=customer_phone,
            service_name=service_name,
            booking_date=booking_date,
            booking_time=booking_time
        )
        
        booking = crud.create_booking(db=db, booking=booking_in, owner_id=owner.id)

        # Send email notifications
        owner_email_subject = env.gettext(f"New Booking for {owner.business_name}!")
        owner_email_body = env.gettext(f"""
            Hello {owner.name},<br><br>
            You have a new booking:<br>
            Customer: {booking.customer_name}<br>
            Email: {booking.customer_email}<br>
            Phone: {booking.customer_phone or 'N/A'}<br>
            Service: {booking.service_name}<br>
            Date: {booking.booking_date.strftime('%Y-%m-%d')}<br>
            Time: {booking.booking_time}<br><br>
            Thank you!
        """)
        notifications.send_email(owner.email, owner_email_subject, owner_email_body)

        customer_email_subject = env.gettext(f"Your Booking with {owner.business_name} is Confirmed!")
        customer_email_body = env.gettext(f"""
            Hello {booking.customer_name},<br><br>
            Your booking with {owner.business_name} has been confirmed:<br>
            Service: {booking.service_name}<br>
            Date: {booking.booking_date.strftime('%Y-%m-%d')}<br>
            Time: {booking.booking_time}<br><br>
            We look forward to seeing you!<br>
            {owner.business_name}
        """)
        notifications.send_email(booking.customer_email, customer_email_subject, customer_email_body)

        # Send WhatsApp notification to owner
        if owner.phone:
            whatsapp_message = env.gettext(f"New Booking for {owner.business_name}:\nCustomer: {booking.customer_name}\nService: {booking.service_name}\nDate: {booking.booking_date.strftime('%Y-%m-%d')}\nTime: {booking.booking_time}")
            notifications.send_whatsapp_message(owner.phone, whatsapp_message)

        return env.get_template("booking_confirmation.html").render({
            "request": request,
            "booking": booking,
            "owner": owner
        })
    except ValueError as ve:
        logger.error(f"Booking submission validation error: {ve}")
        return env.get_template("booking_page.html").render({
            "request": request,
            "owner": owner,
            "services": json.loads(owner.services_json),
            "availability": json.loads(owner.availability_json),
            "error": env.gettext(f"Invalid input: {ve}")
        })
    except Exception as e:
        logger.error(f"Error submitting booking for slug {owner_slug}: {e}")
        return env.get_template("booking_page.html").render({
            "request": request,
            "owner": owner,
            "services": json.loads(owner.services_json),
            "availability": json.loads(owner.availability_json),
            "error": env.gettext("An unexpected error occurred during booking.")
        })

# --- Language Toggle ---
@app.get("/set_language/{lang}", response_class=RedirectResponse)
async def set_language(lang: str, request: Request, response: Response):
    response = RedirectResponse(url=request.headers.get("referer", "/"), status_code=status.HTTP_302_FOUND)
    response.set_cookie(key="lang", value=lang, httponly=False) # httponly=False so JS can read it if needed
    return response

# Error handling middleware
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    env = get_template_env(request)
    template = env.get_template("error.html")
    return HTMLResponse(
        template.render({"request": request, "error_code": exc.status_code, "error_detail": exc.detail}),
        status_code=exc.status_code
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    env = get_template_env(request)
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    template = env.get_template("error.html")
    return HTMLResponse(
        template.render({"request": request, "error_code": 500, "error_detail": env.gettext("An unexpected error occurred.")}),
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
    )
