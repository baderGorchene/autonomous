from fastapi import FastAPI, Depends, Request, Response, Form, HTTPException, status, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from . import crud, models, schemas, security, notifications
from .database import engine, get_db, create_tables
from .dependencies import get_current_owner
from .i18n_config import get_jinja_templates, TEMPLATES_DIR
from src.config import settings
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
import json
import datetime
import logging
from typing import List, Optional

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Add Session Middleware for language preference
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

# Middleware to set language
class LanguageMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 1. Check query parameter
        lang = request.query_params.get("lang")
        if lang:
            request.session["lang"] = lang
        else:
            # 2. Check session
            lang = request.session.get("lang")
            if not lang:
                # 3. Default to English
                lang = "en"
                request.session["lang"] = lang # Store default

        request.state.lang = lang
        response = await call_next(request)
        return response

app.add_middleware(LanguageMiddleware)

# Dependency to get templates env based on current request locale
def get_templates(request: Request) -> Jinja2Templates:
    return get_jinja_templates(request.state.lang)

@app.on_event("startup")
def on_startup():
    create_tables()

@app.get("/health", response_class=HTMLResponse)
async def health_check():
    return "OK"

@app.get("/", response_class=HTMLResponse)
async def root(request: Request, templates: Jinja2Templates = Depends(get_templates)):
    return templates.TemplateResponse("root.html", {"request": request, "lang": request.state.lang})

# Owner Signup
@app.get("/signup", response_class=HTMLResponse)
async def signup_form(request: Request, templates: Jinja2Templates = Depends(get_templates)):
    return templates.TemplateResponse("signup.html", {"request": request, "lang": request.state.lang})

@app.post("/signup", response_class=HTMLResponse)
async def signup(
    request: Request,
    db: Session = Depends(get_db),
    templates: Jinja2Templates = Depends(get_templates),
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    business_name: str = Form(...),
    slug: str = Form(...),
    phone: Optional[str] = Form(None)
):
    owner = crud.get_owner_by_email(db, email=email)
    if owner:
        return templates.TemplateResponse(
            "signup.html",
            {"request": request, "error": get_jinja_templates(request.state.lang).env.gettext("Email already registered"), "lang": request.state.lang},
            status_code=status.HTTP_400_BAD_REQUEST
        )
    owner = crud.get_owner_by_slug(db, slug=slug)
    if owner:
        return templates.TemplateResponse(
            "signup.html",
            {"request": request, "error": get_jinja_templates(request.state.lang).env.gettext("Business URL already taken"), "lang": request.state.lang},
            status_code=status.HTTP_400_BAD_REQUEST
        )

    try:
        owner_in = schemas.OwnerCreate(
            name=name, email=email, password=password, business_name=business_name, slug=slug, phone=phone
        )
        crud.create_owner(db=db, owner=owner_in)
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        logger.error(f"Signup error: {e}")
        return templates.TemplateResponse(
            "signup.html",
            {"request": request, "error": get_jinja_templates(request.state.lang).env.gettext("An unexpected error occurred during signup."), "lang": request.state.lang},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

# Owner Login
@app.get("/login", response_class=HTMLResponse)
async def login_form(request: Request, templates: Jinja2Templates = Depends(get_templates)):
    return templates.TemplateResponse("login.html", {"request": request, "lang": request.state.lang})

@app.post("/token", response_model=schemas.Token)
async def login_for_access_token(
    response: Response,
    db: Session = Depends(get_db),
    form_data: OAuth2PasswordRequestForm = Depends()
):
    owner = crud.authenticate_owner(db, form_data.username, form_data.password)
    if not owner:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = security.create_access_token(data={"sub": owner.email})
    response.set_cookie(key="access_token", value=access_token, httponly=True, samesite="lax", secure=False) # Set secure=True in production
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/login", response_class=HTMLResponse)
async def process_login(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    templates: Jinja2Templates = Depends(get_templates),
    email: str = Form(...),
    password: str = Form(...)
):
    owner = crud.authenticate_owner(db, email, password)
    if not owner:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": get_jinja_templates(request.state.lang).env.gettext("Incorrect email or password"), "lang": request.state.lang},
            status_code=status.HTTP_401_UNAUTHORIZED
        )
    access_token = security.create_access_token(data={"sub": owner.email})
    response.set_cookie(key="access_token", value=access_token, httponly=True, samesite="lax", secure=False) # Set secure=True in production
    return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/logout")
async def logout(response: Response):
    response.delete_cookie(key="access_token")
    return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)


# Owner Dashboard
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    current_owner: schemas.Owner = Depends(get_current_owner),
    db: Session = Depends(get_db),
    templates: Jinja2Templates = Depends(get_templates)
):
    bookings = crud.get_owner_bookings(db, owner_id=current_owner.id)
    services = json.loads(current_owner.services_json)
    availability = json.loads(current_owner.availability_json)
    
    # Filter bookings to show only upcoming
    now = datetime.datetime.now()
    upcoming_bookings = [
        b for b in bookings 
        if b.booking_date > now.date() or (b.booking_date == now.date() and datetime.datetime.strptime(b.booking_time, "%H:%M").time() >= now.time())
    ]
    
    context = {
        "request": request,
        "owner": current_owner,
        "bookings": upcoming_bookings,
        "services": services,
        "availability": availability,
        "lang": request.state.lang
    }
    return templates.TemplateResponse("dashboard.html", context)

# Update Owner Profile
@app.post("/profile", response_class=HTMLResponse)
async def update_profile(
    request: Request,
    current_owner: schemas.Owner = Depends(get_current_owner),
    db: Session = Depends(get_db),
    templates: Jinja2Templates = Depends(get_templates),
    name: str = Form(...),
    business_name: str = Form(...),
    phone: Optional[str] = Form(None)
):
    try:
        owner_update = schemas.OwnerProfileUpdate(name=name, business_name=business_name, phone=phone)
        crud.update_owner_profile(db, current_owner, owner_update)
        return RedirectResponse(url="/dashboard?success=profile_updated", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        logger.error(f"Profile update error: {e}")
        bookings = crud.get_owner_bookings(db, owner_id=current_owner.id)
        services = json.loads(current_owner.services_json)
        availability = json.loads(current_owner.availability_json)
        
        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "owner": current_owner,
                "bookings": bookings,
                "services": services,
                "availability": availability,
                "error": get_jinja_templates(request.state.lang).env.gettext("Failed to update profile."),
                "lang": request.state.lang
            },
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

# Update Services
@app.post("/services", response_class=HTMLResponse)
async def update_services(
    request: Request,
    current_owner: models.Owner = Depends(get_current_owner),
    db: Session = Depends(get_db),
    templates: Jinja2Templates = Depends(get_templates),
    services_data: str = Form(..., alias="services") # Expecting JSON string
):
    try:
        services_list = json.loads(services_data)
        # Validate services_list against schemas.Service
        validated_services = [schemas.Service(**s).model_dump() for s in services_list]
        current_owner.services_json = json.dumps(validated_services)
        db.add(current_owner)
        db.commit()
        db.refresh(current_owner)
        return RedirectResponse(url="/dashboard?success=services_updated", status_code=status.HTTP_303_SEE_OTHER)
    except json.JSONDecodeError:
        error_msg = get_jinja_templates(request.state.lang).env.gettext("Invalid JSON format for services.")
        logger.error(f"Invalid JSON for services: {services_data}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_msg)
    except Exception as e:
        logger.error(f"Error updating services: {e}")
        error_msg = get_jinja_templates(request.state.lang).env.gettext("Failed to update services.")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=error_msg)

# Update Availability
@app.post("/availability", response_class=HTMLResponse)
async def update_availability(
    request: Request,
    current_owner: models.Owner = Depends(get_current_owner),
    db: Session = Depends(get_db),
    templates: Jinja2Templates = Depends(get_templates),
    availability_data: str = Form(..., alias="availability") # Expecting JSON string
):
    try:
        availability_dict = json.loads(availability_data)
        # Validate availability_dict against schemas.OwnerAvailability
        # This part might need more robust validation for nested lists of AvailabilitySlot
        # For simplicity, we'll just store it as is after basic JSON check.
        # A more thorough validation would iterate through days and slots.
        # For now, let's just ensure it's a dict.
        if not isinstance(availability_dict, dict):
             raise ValueError("Availability data must be a dictionary.")

        current_owner.availability_json = json.dumps(availability_dict)
        db.add(current_owner)
        db.commit()
        db.refresh(current_owner)
        return RedirectResponse(url="/dashboard?success=availability_updated", status_code=status.HTTP_303_SEE_OTHER)
    except json.JSONDecodeError:
        error_msg = get_jinja_templates(request.state.lang).env.gettext("Invalid JSON format for availability.")
        logger.error(f"Invalid JSON for availability: {availability_data}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_msg)
    except Exception as e:
        logger.error(f"Error updating availability: {e}")
        error_msg = get_jinja_templates(request.state.lang).env.gettext("Failed to update availability.")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=error_msg)


# Public Booking Page
@app.get("/{owner_slug}", response_class=HTMLResponse)
async def public_booking_page(
    owner_slug: str,
    request: Request,
    db: Session = Depends(get_db),
    templates: Jinja2Templates = Depends(get_templates)
):
    owner = crud.get_owner_by_slug(db, slug=owner_slug)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking page not found")

    services = json.loads(owner.services_json)
    availability = json.loads(owner.availability_json)

    context = {
        "request": request,
        "owner": owner,
        "services": services,
        "availability": availability,
        "lang": request.state.lang
    }
    return templates.TemplateResponse("booking_page.html", context)


@app.post("/{owner_slug}/book", response_class=HTMLResponse)
async def submit_booking(
    owner_slug: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    templates: Jinja2Templates = Depends(get_templates),
    customer_name: str = Form(...),
    customer_email: str = Form(...),
    customer_phone: Optional[str] = Form(None),
    service_name: str = Form(...),
    booking_date: str = Form(...), # YYYY-MM-DD
    booking_time: str = Form(...)  # HH:MM
):
    owner = crud.get_owner_by_slug(db, slug=owner_slug)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking page not found")

    try:
        parsed_date = datetime.datetime.strptime(booking_date, "%Y-%m-%d").date()
        parsed_time = datetime.datetime.strptime(booking_time, "%H:%M").time()
        
        # Basic validation: Check if booking date is in the future
        if parsed_date < datetime.date.today():
             raise ValueError(get_jinja_templates(request.state.lang).env.gettext("Booking date cannot be in the past."))
        if parsed_date == datetime.date.today() and parsed_time <= datetime.datetime.now().time():
             raise ValueError(get_jinja_templates(request.state.lang).env.gettext("Booking time cannot be in the past."))

        # Further validation: Check if the service exists and if the time slot is available
        services = json.loads(owner.services_json)
        if not any(s['name'] == service_name for s in services):
            raise ValueError(get_jinja_templates(request.state.lang).env.gettext("Selected service is not available."))
        
        # This is a simplified availability check. A real app would check for overlaps, etc.
        # For MVP, we assume any time slot within declared availability for the day is fine.
        day_of_week = parsed_date.strftime('%A')
        availability = json.loads(owner.availability_json)
        
        is_available = False
        if day_of_week in availability:
            for slot in availability[day_of_week]:
                slot_start = datetime.datetime.strptime(slot['start_time'], "%H:%M").time()
                slot_end = datetime.datetime.strptime(slot['end_time'], "%H:%M").time()
                if slot_start <= parsed_time < slot_end:
                    is_available = True
                    break
        
        if not is_available:
            raise ValueError(get_jinja_templates(request.state.lang).env.gettext("The selected time slot is not available."))


        booking_in = schemas.BookingCreate(
            customer_name=customer_name,
            customer_email=customer_email,
            customer_phone=customer_phone,
            service_name=service_name,
            booking_date=parsed_date,
            booking_time=booking_time # Store as HH:MM string
        )
        
        db_booking = crud.create_booking(db, booking_in, owner.id)

        booking_details = booking_in.model_dump() # Use model_dump for Pydantic v2
        booking_details['booking_date'] = parsed_date # Ensure date object is passed for formatting

        # Send notifications in the background
        background_tasks.add_task(
            notifications.send_booking_confirmation_notifications,
            owner_email=owner.email,
            owner_phone=owner.phone,
            customer_email=customer_email,
            customer_phone=customer_phone,
            booking_details=booking_details,
            locale=request.state.lang
        )

        return templates.TemplateResponse(
            "booking_confirmation.html",
            {"request": request, "booking": db_booking, "owner": owner, "lang": request.state.lang}
        )
    except ValueError as ve:
        logger.error(f"Booking validation error: {ve}")
        services = json.loads(owner.services_json)
        availability = json.loads(owner.availability_json)
        return templates.TemplateResponse(
            "booking_page.html",
            {
                "request": request,
                "owner": owner,
                "services": services,
                "availability": availability,
                "error": str(ve),
                "form_data": { # Repopulate form with user input
                    "customer_name": customer_name,
                    "customer_email": customer_email,
                    "customer_phone": customer_phone,
                    "service_name": service_name,
                    "booking_date": booking_date,
                    "booking_time": booking_time,
                },
                "lang": request.state.lang
            },
            status_code=status.HTTP_400_BAD_REQUEST
        )
    except Exception as e:
        logger.error(f"Error submitting booking: {e}")
        services = json.loads(owner.services_json)
        availability = json.loads(owner.availability_json)
        return templates.TemplateResponse(
            "booking_page.html",
            {
                "request": request,
                "owner": owner,
                "services": services,
                "availability": availability,
                "error": get_jinja_templates(request.state.lang).env.gettext("An unexpected error occurred during booking."),
                "form_data": { # Repopulate form with user input
                    "customer_name": customer_name,
                    "customer_email": customer_email,
                    "customer_phone": customer_phone,
                    "service_name": service_name,
                    "booking_date": booking_date,
                    "booking_time": booking_time,
                },
                "lang": request.state.lang
            },
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

# API endpoint to get available slots for a given date (for dynamic updates on booking page)
@app.get("/{owner_slug}/available-slots/{date}", response_model=List[str])
async def get_available_slots(
    owner_slug: str,
    date: str, # YYYY-MM-DD
    db: Session = Depends(get_db),
    request: Request = Depends(get_templates) # Used for i18n
):
    owner = crud.get_owner_by_slug(db, slug=owner_slug)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Owner not found")

    try:
        parsed_date = datetime.datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid date format. Use YYYY-MM-DD.")
    
    # Filter for future dates
    if parsed_date < datetime.date.today():
        return []

    day_of_week = parsed_date.strftime('%A') # e.g., "Monday"
    availability = json.loads(owner.availability_json)
    
    possible_slots = []
    if day_of_week in availability:
        for slot_range in availability[day_of_week]:
            start_time_str = slot_range['start_time']
            end_time_str = slot_range['end_time']
            
            start_dt = datetime.datetime.combine(parsed_date, datetime.datetime.strptime(start_time_str, "%H:%M").time())
            end_dt = datetime.datetime.combine(parsed_date, datetime.datetime.strptime(end_time_str, "%H:%M").time())
            
            # Generate 30-minute slots
            current_slot_dt = start_dt
            while current_slot_dt < end_dt:
                # Only add slots in the future if it's today
                if parsed_date == datetime.date.today() and current_slot_dt.time() <= datetime.datetime.now().time():
                    current_slot_dt += datetime.timedelta(minutes=30)
                    continue
                possible_slots.append(current_slot_dt.strftime("%H:%M"))
                current_slot_dt += datetime.timedelta(minutes=30)
    
    # In a real application, you'd also check for existing bookings to remove taken slots.
    # For MVP, we assume all declared available slots are bookable.
    
    return possible_slots
