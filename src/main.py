from datetime import date, timedelta, time, datetime
from typing import List, Optional, Dict, Any
import calendar
import json # For JSON-LD

from fastapi import FastAPI, Depends, HTTPException, status, Request, Form, Query, APIRouter
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import func, extract
from starlette.middleware.sessions import SessionMiddleware
from starlette.routing import Mount
from starlette.applications import Starlette

from . import models, schemas, security, notifications, analytics, availability_utils
from .database import SessionLocal, engine
from .config import settings

# For i18n
import gettext
import os
from babel.numbers import format_currency as babel_format_currency

models.Base.metadata.create_all(bind=engine)

app = FastAPI()

# Add SessionMiddleware for flash messages and language selection
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

# Static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Templates setup
templates_dir = os.path.join(os.path.dirname(__file__), "../templates")
locales_dir = os.path.join(os.path.dirname(__file__), "../locales")
templates = Jinja2Templates(directory=templates_dir)

# i18n setup
@app.middleware("http")
async def add_i18n_middleware(request: Request, call_next):
    lang = request.session.get("lang", "en")
    request.state.lang = lang

    # Initialize gettext for the request
    try:
        t = gettext.translation("messages", locales_dir, languages=[lang], fallback=True)
        request.state.gettext = t.gettext
        request.state.ngettext = t.ngettext
    except FileNotFoundError:
        # Fallback to default if translation file is not found
        request.state.gettext = gettext.gettext
        request.state.ngettext = gettext.ngettext

    response = await call_next(request)
    return response

# Jinja2 globals for i18n and other utilities
def _(message: str):
    # This is a basic way to get the request object in a global filter/function.
    # In a real app, you might pass a context dict or use a custom Jinja2 Environment loader
    # that injects the request.state.gettext more directly.
    # For this agent's purpose, this direct access is acceptable given the constraints.
    current_request = getattr(templates.env.globals.get('request'), 'state', None)
    if current_request and hasattr(current_request, "gettext"):
        return current_request.gettext(message)
    return message

def format_currency_filter(value, currency, locale):
    try:
        # Get language code from locale (e.g., 'en' from 'en_US')
        lang_code = locale.split('_')[0] if locale else 'en'
        return babel_format_currency(value, currency, locale=lang_code)
    except Exception as e:
        print(f"Error formatting currency: {e}")
        return f"{currency} {value:.2f}"

templates.env.filters['format_currency'] = format_currency_filter
templates.env.globals["_"] = _
templates.env.globals["get_flashed_messages"] = lambda request: request.session.pop("flash_messages", [])
templates.env.globals["url_for"] = app.url_path_for # Make url_for available in templates
templates.env.globals["json"] = json # Make json module available for JSON-LD

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

router = APIRouter()

@router.get("/health")
async def health_check():
    return {"status": "ok"}

# Authentication endpoints
@router.post("/token", response_model=schemas.Token)
async def login_for_access_token(db: Session = Depends(get_db), form_data: OAuth2PasswordRequestForm = Depends()):
    owner = security.authenticate_owner(db, form_data.username, form_data.password)
    if not owner:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": owner.email}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/signup", response_model=schemas.Owner)
async def signup(owner: schemas.OwnerCreate, db: Session = Depends(get_db)):
    db_owner = db.query(models.Owner).filter(models.Owner.email == owner.email).first()
    if db_owner:
        raise HTTPException(status_code=400, detail="Email already registered")
    hashed_password = security.get_password_hash(owner.password)
    db_owner = models.Owner(
        email=owner.email,
        hashed_password=hashed_password,
        name=owner.name,
        username=owner.username, # Assuming username is part of signup
        phone_number=owner.phone_number,
        description=owner.description, # New field
        city=owner.city, # New field
        country=owner.country # New field
    )
    db.add(db_owner)
    db.commit()
    db.refresh(db_owner)
    return db_owner

# Owner Dashboard
@router.get("/dashboard", response_class=HTMLResponse)
async def owner_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    current_owner: schemas.Owner = Depends(security.get_current_active_owner)
):
    # Fetch data for dashboard
    services = db.query(models.Service).filter(models.Service.owner_id == current_owner.id).all()
    upcoming_bookings = db.query(models.Booking).filter(
        models.Booking.owner_id == current_owner.id,
        models.Booking.date >= date.today()
    ).order_by(models.Booking.date, models.Booking.time).all()

    # Analytics data
    monthly_bookings = analytics.get_monthly_bookings_data(db, current_owner.id)
    popular_services = analytics.get_popular_services_data(db, current_owner.id)

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "owner": current_owner,
            "services": services,
            "upcoming_bookings": upcoming_bookings,
            "monthly_bookings": monthly_bookings,
            "popular_services": popular_services,
            "__": request.state.gettext # Pass gettext function to template
        }
    )

@router.post("/dashboard/profile", response_class=HTMLResponse)
async def update_owner_profile(
    request: Request,
    db: Session = Depends(get_db),
    current_owner: schemas.Owner = Depends(security.get_current_active_owner),
    name: str = Form(...),
    phone_number: str = Form(...),
    description: Optional[str] = Form(None),
    city: Optional[str] = Form(None),
    country: Optional[str] = Form(None)
):
    try:
        current_owner.name = name
        current_owner.phone_number = phone_number
        current_owner.description = description
        current_owner.city = city
        current_owner.country = country
        db.add(current_owner)
        db.commit()
        db.refresh(current_owner)
        request.session.setdefault("flash_messages", []).append({"type": "success", "message": request.state.gettext("Profile updated successfully!")})
    except Exception as e:
        db.rollback()
        request.session.setdefault("flash_messages", []).append({"type": "error", "message": request.state.gettext(f"Error updating profile: {e}")})
    return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)

# Service Management
@router.post("/dashboard/services", response_class=HTMLResponse)
async def add_service(
    request: Request,
    db: Session = Depends(get_db),
    current_owner: schemas.Owner = Depends(security.get_current_active_owner),
    name: str = Form(...),
    description: Optional[str] = Form(None),
    duration_minutes: int = Form(...),
    price: float = Form(...),
    currency: str = Form("USD"),
    category: Optional[str] = Form(None) # New field
):
    try:
        service_slug = name.lower().replace(" ", "-") # Simple slug generation
        db_service = models.Service(
            owner_id=current_owner.id,
            name=name,
            description=description,
            duration_minutes=duration_minutes,
            price=price,
            currency=currency,
            slug=service_slug,
            category=category
        )
        db.add(db_service)
        db.commit()
        db.refresh(db_service)
        request.session.setdefault("flash_messages", []).append({"type": "success", "message": request.state.gettext("Service added successfully!")})
    except Exception as e:
        db.rollback()
        request.session.setdefault("flash_messages", []).append({"type": "error", "message": request.state.gettext(f"Error adding service: {e}")})
    return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)

# Availability Management (simplified)
@router.post("/dashboard/availability", response_class=HTMLResponse)
async def add_availability(
    request: Request,
    db: Session = Depends(get_db),
    current_owner: schemas.Owner = Depends(security.get_current_active_owner),
    service_id: Optional[int] = Form(None),
    date_str: Optional[str] = Form(None),
    start_time_str: str = Form(...),
    end_time_str: str = Form(...),
    recurrence_type: Optional[str] = Form(None),
    recurrence_value: Optional[str] = Form(None),
    recurrence_start_date_str: Optional[str] = Form(None),
    recurrence_end_date_str: Optional[str] = Form(None)
):
    try:
        start_time = datetime.strptime(start_time_str, "%H:%M").time()
        end_time = datetime.strptime(end_time_str, "%H:%M").time()
        
        availability_date = datetime.strptime(date_str, "%Y-%m-%d").date() if date_str else None
        recurrence_start_date = datetime.strptime(recurrence_start_date_str, "%Y-%m-%d").date() if recurrence_start_date_str else None
        recurrence_end_date = datetime.strptime(recurrence_end_date_str, "%Y-%m-%d").date() if recurrence_end_date_str else None

        db_availability = models.Availability(
            owner_id=current_owner.id,
            service_id=service_id,
            date=availability_date,
            start_time=start_time,
            end_time=end_time,
            recurrence_type=recurrence_type.upper() if recurrence_type else None,
            recurrence_value=recurrence_value,
            recurrence_start_date=recurrence_start_date,
            recurrence_end_date=recurrence_end_date
        )
        db.add(db_availability)
        db.commit()
        db.refresh(db_availability)
        request.session.setdefault("flash_messages", []).append({"type": "success", "message": request.state.gettext("Availability added successfully!")})
    except Exception as e:
        db.rollback()
        request.session.setdefault("flash_messages", []).append({"type": "error", "message": request.state.gettext(f"Error adding availability: {e}")})
    return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)

# Public Booking Page
@router.get("/book/{owner_username}/{service_slug}", response_class=HTMLResponse)
async def get_booking_page(
    owner_username: str,
    service_slug: str,
    request: Request,
    db: Session = Depends(get_db),
    lang: Optional[str] = Query(None)
):
    if lang:
        request.session["lang"] = lang
        # Reload gettext for current request if language changed via query param
        try:
            t = gettext.translation("messages", locales_dir, languages=[lang], fallback=True)
            request.state.gettext = t.gettext
            request.state.ngettext = t.ngettext
        except FileNotFoundError:
            request.state.gettext = gettext.gettext
            request.state.ngettext = gettext.ngettext

    owner = db.query(models.Owner).filter(models.Owner.username == owner_username).first()
    if not owner:
        raise HTTPException(status_code=404, detail=request.state.gettext("Owner not found"))

    service = db.query(models.Service).filter(
        models.Service.owner_id == owner.id,
        models.Service.slug == service_slug
    ).first()
    if not service:
        raise HTTPException(status_code=404, detail=request.state.gettext("Service not found"))
    
    # Fetch reviews for the service
    reviews = db.query(models.Review).filter(
        models.Review.service_id == service.id
    ).order_by(models.Review.created_at.desc()).all()

    # Get average rating
    avg_rating_result = db.query(func.avg(models.Review.rating)).filter(
        models.Review.service_id == service.id
    ).scalar()
    average_rating = round(avg_rating_result, 1) if avg_rating_result else None


    # Prepare a default date for the calendar
    today = date.today()
    
    # Calculate available slot duration (assuming it's the service duration)
    slot_duration_minutes = service.duration_minutes

    return templates.TemplateResponse(
        "booking_page.html",
        {
            "request": request,
            "owner": owner,
            "service": service,
            "today_date": today.isoformat(),
            "slot_duration": slot_duration_minutes,
            "reviews": reviews,
            "average_rating": average_rating,
            "__": request.state.gettext # Pass gettext function to template
        }
    )

@router.post("/book/{owner_username}/{service_slug}/submit", response_class=HTMLResponse)
async def submit_booking(
    owner_username: str,
    service_slug: str,
    request: Request,
    db: Session = Depends(get_db),
    customer_name: str = Form(...),
    customer_email: str = Form(...),
    customer_phone: Optional[str] = Form(None),
    booking_date: str = Form(...),
    booking_time: str = Form(...),
    is_recurring: bool = Form(False),
    recurrence_end_date: Optional[str] = Form(None)
):
    owner = db.query(models.Owner).filter(models.Owner.username == owner_username).first()
    if not owner:
        raise HTTPException(status_code=404, detail=request.state.gettext("Owner not found"))

    service = db.query(models.Service).filter(
        models.Service.owner_id == owner.id,
        models.Service.slug == service_slug
    ).first()
    if not service:
        raise HTTPException(status_code=404, detail=request.state.gettext("Service not found"))
    
    try:
        parsed_date = datetime.strptime(booking_date, "%Y-%m-%d").date()
        parsed_time = datetime.strptime(booking_time, "%H:%M").time()
        
        # Check if the slot is actually available
        available_slots = availability_utils.get_available_slots_for_day(
            db, owner.id, service.id, parsed_date, service.duration_minutes
        )
        if parsed_time not in available_slots:
            raise HTTPException(status_code=400, detail=request.state.gettext("Selected slot is not available or already booked."))

        db_booking = models.Booking(
            owner_id=owner.id,
            service_id=service.id,
            customer_name=customer_name,
            customer_email=customer_email,
            customer_phone=customer_phone,
            date=parsed_date,
            time=parsed_time,
            is_recurring=is_recurring,
            recurrence_end_date=datetime.strptime(recurrence_end_date, "%Y-%m-%d").date() if is_recurring and recurrence_end_date else None
        )
        db.add(db_booking)
        db.commit()
        db.refresh(db_booking)

        # Send notifications
        notifications.send_booking_confirmation(owner, service, db_booking)
        notifications.send_booking_notification_to_owner(owner, service, db_booking)

        return templates.TemplateResponse(
            "booking_confirmation.html",
            {
                "request": request,
                "booking": db_booking,
                "owner": owner,
                "service": service,
                "__": request.state.gettext
            }
        )
    except ValueError:
        raise HTTPException(status_code=400, detail=request.state.gettext("Invalid date or time format."))
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=request.state.gettext(f"An error occurred: {e}"))

# API endpoint to fetch available slots for a specific date
@router.get("/api/available_slots/{owner_username}/{service_slug}/{target_date_str}", response_model=List[schemas.TimeSlot])
async def get_available_slots_api(
    owner_username: str,
    service_slug: str,
    target_date_str: str,
    db: Session = Depends(get_db)
):
    owner = db.query(models.Owner).filter(models.Owner.username == owner_username).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")

    service = db.query(models.Service).filter(
        models.Service.owner_id == owner.id,
        models.Service.slug == service_slug
    ).first()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    
    try:
        target_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")

    available_times = availability_utils.get_available_slots_for_day(
        db, owner.id, service.id, target_date, service.duration_minutes
    )
    return [{"time": t.isoformat()} for t in available_times]


# Language toggle endpoint
@router.get("/set_lang/{lang_code}", response_class=RedirectResponse)
async def set_language(request: Request, lang_code: str):
    request.session["lang"] = lang_code
    # Redirect to the page the user came from, or to dashboard as a fallback
    redirect_url = request.headers.get("referer", "/dashboard")
    return RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)


# Customer specific endpoints (simplified)
@router.post("/customer/signup", response_model=schemas.Customer)
async def customer_signup(customer: schemas.CustomerCreate, db: Session = Depends(get_db)):
    db_customer = db.query(models.Customer).filter(models.Customer.email == customer.email).first()
    if db_customer:
        raise HTTPException(status_code=400, detail="Email already registered")
    hashed_password = security.get_password_hash(customer.password)
    db_customer = models.Customer(
        email=customer.email,
        hashed_password=hashed_password,
        name=customer.name,
        phone_number=customer.phone_number
    )
    db.add(db_customer)
    db.commit()
    db.refresh(db_customer)
    return db_customer

@router.post("/customer/token", response_model=schemas.Token)
async def customer_login_for_access_token(db: Session = Depends(get_db), form_data: OAuth2PasswordRequestForm = Depends()):
    customer = security.authenticate_customer(db, form_data.username, form_data.password)
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": customer.email, "user_type": "customer"}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/customer/profile", response_model=schemas.Customer)
async def get_customer_profile(
    db: Session = Depends(get_db),
    current_customer: schemas.Customer = Depends(security.get_current_active_customer)
):
    return current_customer

@router.put("/customer/profile", response_model=schemas.Customer)
async def update_customer_profile(
    customer_update: schemas.CustomerUpdate,
    db: Session = Depends(get_db),
    current_customer: schemas.Customer = Depends(security.get_current_active_customer)
):
    for field, value in customer_update.dict(exclude_unset=True).items():
        setattr(current_customer, field, value)
    db.add(current_customer)
    db.commit()
    db.refresh(current_customer)
    return current_customer

# Review submission endpoint
@router.post("/api/reviews/{service_id}", response_model=schemas.Review)
async def submit_review_api(
    service_id: int,
    review_data: schemas.ReviewCreate,
    db: Session = Depends(get_db),
    current_customer: schemas.Customer = Depends(security.get_current_active_customer)
):
    service = db.query(models.Service).filter(models.Service.id == service_id).first()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")

    db_review = models.Review(
        service_id=service_id,
        customer_id=current_customer.id,
        rating=review_data.rating,
        comment=review_data.comment
    )
    db.add(db_review)
    db.commit()
    db.refresh(db_review)
    return db_review

app.include_router(router)
