from fastapi import FastAPI, Depends, HTTPException, status, Request, Response, Form, BackgroundTasks
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import timedelta, datetime, date
from typing import List, Optional, Dict, Any
import json
import logging

from . import models, schemas, crud, security, notifications
from .database import SessionLocal, engine, create_tables, get_db
from .config import settings
from .i18n_config import get_jinja_env

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create database tables on startup
# This is typically done with migrations in production, but for MVP, this is fine.
create_tables()

app = FastAPI(
    title="BookSlot API",
    description="API for the BookSlot booking page application.",
    version="0.1.0",
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Dependency to get the current owner from the JWT token
async def get_current_owner(request: Request, db: Session = Depends(get_db)) -> models.Owner:
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token_data = security.decode_access_token(token)
    if token_data is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    owner = crud.get_owner_by_email(db, email=token_data.get("sub"))
    if owner is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Owner not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return owner

# Dependency for translations
def get_locale(request: Request) -> str:
    # Prioritize query parameter, then cookie, then accept-language header, fallback to 'en'
    query_locale = request.query_params.get("lang")
    if query_locale in ["en", "ar", "fr"]:
        return query_locale
    
    cookie_locale = request.cookies.get("lang")
    if cookie_locale in ["en", "ar", "fr"]:
        return cookie_locale
        
    accept_language = request.headers.get("Accept-Language", "en")
    if "ar" in accept_language:
        return "ar"
    if "fr" in accept_language:
        return "fr"
    return "en"

@app.middleware("http")
async def add_language_middleware(request: Request, call_next):
    locale = get_locale(request)
    request.state.locale = locale
    response = await call_next(request)
    # Set cookie if not already set, or if query param changed it
    if request.cookies.get("lang") != locale:
        response.set_cookie(key="lang", value=locale, httponly=True, samesite="lax", max_age=3600 * 24 * 30) # 30 days
    return response

# Template setup with i18n
def get_templates(request: Request) -> Jinja2Templates:
    locale = request.state.locale if hasattr(request.state, 'locale') else 'en'
    env = get_jinja_env(locale)
    return Jinja2Templates(directory=settings.TEMPLATES_DIR, env=env)

# --- API Endpoints ---

@app.post("/token", response_model=schemas.Token)
async def login_for_access_token(response: Response, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
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
    response.set_cookie(key="access_token", value=access_token, httponly=True, samesite="lax")
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/health", response_class=HTMLResponse)
async def health_check():
    return "OK"

# --- HTML/UI Routes ---

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request, templates: Jinja2Templates = Depends(get_templates)):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request, templates: Jinja2Templates = Depends(get_templates)):
    return templates.TemplateResponse("signup.html", {"request": request})

@app.post("/signup", response_class=RedirectResponse, status_code=status.HTTP_303_SEE_OTHER)
async def signup_owner(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    business_name: str = Form(...),
    slug: str = Form(...),
    phone: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    owner = crud.get_owner_by_email(db, email=email)
    if owner:
        # TODO: Add error message to template
        raise HTTPException(status_code=400, detail="Email already registered")
    owner_by_slug = crud.get_owner_by_slug(db, slug=slug)
    if owner_by_slug:
        # TODO: Add error message to template
        raise HTTPException(status_code=400, detail="Booking page URL already taken")
    
    try:
        owner_create = schemas.OwnerCreate(
            name=name, email=email, password=password, business_name=business_name, slug=slug, phone=phone
        )
        db_owner = crud.create_owner(db=db, owner=owner_create)
    except Exception as e:
        logger.error(f"Error creating owner: {e}")
        # TODO: Add error message to template
        raise HTTPException(status_code=400, detail="Error creating owner. Please check your inputs.")

    # Log in the user automatically after signup
    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": db_owner.email}, expires_delta=access_token_expires
    )
    response.set_cookie(key="access_token", value=access_token, httponly=True, samesite="lax")
    return response

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, templates: Jinja2Templates = Depends(get_templates)):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login", response_class=RedirectResponse, status_code=status.HTTP_303_SEE_OTHER)
async def login_owner(
    response: Response,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    owner = crud.authenticate_owner(db, email, password)
    if not owner:
        # TODO: Add error message to template
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": owner.email}, expires_delta=access_token_expires
    )
    response.set_cookie(key="access_token", value=access_token, httponly=True, samesite="lax")
    return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/logout", response_class=RedirectResponse, status_code=status.HTTP_303_SEE_OTHER)
async def logout_owner(response: Response):
    response.delete_cookie(key="access_token")
    return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/dashboard", response_class=HTMLResponse)
async def owner_dashboard(
    request: Request,
    templates: Jinja2Templates = Depends(get_templates),
    current_owner: models.Owner = Depends(get_current_owner),
    db: Session = Depends(get_db)
):
    bookings = crud.get_owner_bookings(db, current_owner.id)
    upcoming_bookings = [
        b for b in bookings if b.booking_date >= date.today()
    ]
    
    # Parse services and availability for display
    services = json.loads(current_owner.services_json) if current_owner.services_json else []
    availability = json.loads(current_owner.availability_json) if current_owner.availability_json else {}

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "owner": current_owner,
            "bookings": upcoming_bookings,
            "services": services,
            "availability": availability,
            "booking_page_url": f"bookslot.app/{current_owner.slug}" # Placeholder, needs actual domain
        }
    )

@app.get("/profile", response_class=HTMLResponse)
async def owner_profile_page(
    request: Request,
    templates: Jinja2Templates = Depends(get_templates),
    current_owner: models.Owner = Depends(get_current_owner)
):
    services = json.loads(current_owner.services_json) if current_owner.services_json else []
    availability = json.loads(current_owner.availability_json) if current_owner.availability_json else {}
    return templates.TemplateResponse(
        "profile.html",
        {
            "request": request,
            "owner": current_owner,
            "services": services,
            "availability": availability
        }
    )

@app.post("/profile", response_class=RedirectResponse, status_code=status.HTTP_303_SEE_OTHER)
async def update_owner_profile(
    request: Request,
    name: str = Form(...),
    business_name: str = Form(...),
    phone: Optional[str] = Form(None),
    services_json: str = Form("[]"), # Expecting JSON string from a hidden input or JS
    availability_json: str = Form("{}"), # Expecting JSON string from a hidden input or JS
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(get_current_owner)
):
    try:
        # Validate services_json and availability_json
        services_data = json.loads(services_json)
        availability_data = json.loads(availability_json)

        # Basic validation for services
        for service in services_data:
            schemas.Service(**service) # Validate each service item

        # Basic validation for availability
        for day, slots in availability_data.items():
            for slot in slots:
                schemas.AvailabilitySlot(**slot) # Validate each slot

        owner_update = schemas.OwnerProfileUpdate(
            name=name,
            business_name=business_name,
            phone=phone,
            services=services_data,
            availability=availability_data
        )
        
        updated_owner = crud.update_owner_profile(db, current_owner, owner_update)
        # Update services_json and availability_json directly as they are Text fields
        updated_owner.services_json = services_json
        updated_owner.availability_json = availability_json
        db.add(updated_owner)
        db.commit()
        db.refresh(updated_owner)

    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON format for services or availability.")
    except Exception as e:
        logger.error(f"Error updating owner profile: {e}")
        raise HTTPException(status_code=400, detail=f"Error updating profile: {e}")
    
    return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/bookslot.app/{owner_slug}", response_class=HTMLResponse)
async def public_booking_page(
    request: Request,
    owner_slug: str,
    templates: Jinja2Templates = Depends(get_templates),
    db: Session = Depends(get_db)
):
    owner = crud.get_owner_by_slug(db, owner_slug)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking page not found")

    services = json.loads(owner.services_json) if owner.services_json else []
    availability = json.loads(owner.availability_json) if owner.availability_json else {}

    return templates.TemplateResponse(
        "booking_page.html",
        {
            "request": request,
            "owner": owner,
            "services": services,
            "availability": availability
        }
    )

@app.post("/bookslot.app/{owner_slug}/book", response_class=RedirectResponse, status_code=status.HTTP_303_SEE_OTHER)
async def submit_booking(
    request: Request,
    owner_slug: str,
    background_tasks: BackgroundTasks,
    customer_name: str = Form(...),
    customer_email: str = Form(...),
    customer_phone: Optional[str] = Form(None),
    service_name: str = Form(...),
    booking_date_str: str = Form(...),
    booking_time: str = Form(...),
    db: Session = Depends(get_db)
):
    owner = crud.get_owner_by_slug(db, owner_slug)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking page not found")

    try:
        booking_date = datetime.strptime(booking_date_str, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Expected YYYY-MM-DD.")
    
    # TODO: Add more robust validation for time slot availability
    # For MVP, we assume the frontend sends valid (available) time slots.

    booking_create = schemas.BookingCreate(
        customer_name=customer_name,
        customer_email=customer_email,
        customer_phone=customer_phone,
        service_name=service_name,
        booking_date=booking_date,
        booking_time=booking_time
    )

    try:
        db_booking = crud.create_booking(db, booking_create, owner.id)
        background_tasks.add_task(notifications.notify_owner_of_new_booking, owner, db_booking)
        background_tasks.add_task(notifications.notify_customer_of_booking_confirmation, owner, db_booking)
    except Exception as e:
        logger.error(f"Error creating booking or sending notifications: {e}")
        raise HTTPException(status_code=400, detail="Error processing your booking. Please try again.")

    # Redirect to a confirmation page or show a success message
    return RedirectResponse(url=f"/bookslot.app/{owner_slug}/confirm?booking_id={db_booking.id}", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/bookslot.app/{owner_slug}/confirm", response_class=HTMLResponse)
async def booking_confirmation_page(
    request: Request,
    owner_slug: str,
    booking_id: int,
    templates: Jinja2Templates = Depends(get_templates),
    db: Session = Depends(get_db)
):
    owner = crud.get_owner_by_slug(db, owner_slug)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking page not found")

    booking = db.query(models.Booking).filter(models.Booking.id == booking_id, models.Booking.owner_id == owner.id).first()
    if not booking:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found.")

    return templates.TemplateResponse(
        "booking_confirmation.html",
        {
            "request": request,
            "owner": owner,
            "booking": booking
        }
    )