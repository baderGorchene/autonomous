from fastapi import FastAPI, Depends, HTTPException, status, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import timedelta, datetime
import json
import logging
from typing import List, Dict, Any, Optional

from . import crud, models, schemas, security, notifications
from .database import SessionLocal, engine, get_db, Base, create_tables
from .config import settings
from .i18n_config import get_jinja_env

app = FastAPI()

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# OAuth2PasswordBearer for token authentication
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# --- Internationalization Setup ---
# This will be dynamically set per request based on language cookie/header
# For now, default to English. The actual template rendering will use the request's locale.
templates = Jinja2Templates(directory="templates") # This will be overridden by get_jinja_env

@app.middleware("http")
async def add_i18n_middleware(request: Request, call_next):
    lang = request.cookies.get("lang", "en")
    request.state.gettext = get_jinja_env(locale=lang).gettext
    request.state.ngettext = get_jinja_env(locale=lang).ngettext
    request.state.jinja_env = get_jinja_env(locale=lang)
    response = await call_next(request)
    return response

# Dependency to get the current owner from the token
async def get_current_owner(request: Request, token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=request.state.gettext("Could not validate credentials"),
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = security.decode_access_token(token)
        owner_id: int = payload.get("sub")
        if owner_id is None:
            raise credentials_exception
        token_data = schemas.TokenData(owner_id=owner_id)
    except Exception:
        raise credentials_exception
    owner = crud.get_owner(db, owner_id=token_data.owner_id)
    if owner is None:
        raise credentials_exception
    return owner

# --- Health Check Endpoint ---
@app.get("/health", response_model=Dict[str, str])
def health_check():
    return {"status": "ok"}

# --- Root Redirect to Signup ---
@app.get("/", response_class=RedirectResponse, status_code=status.HTTP_302_FOUND)
async def root():
    return "/signup"

# --- Signup Page ---
@app.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request):
    return request.state.jinja_env.get_template("signup.html").render(request=request)

@app.post("/signup", response_class=HTMLResponse)
async def signup(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    name = form.get("name")
    email = form.get("email")
    password = form.get("password")
    business_name = form.get("business_name")
    phone = form.get("phone")
    slug = form.get("slug")

    # Basic validation
    if not all([name, email, password, business_name, phone, slug]):
        return request.state.jinja_env.get_template("signup.html").render(
            request=request,
            error=request.state.gettext("All fields are required."),
            name=name, email=email, business_name=business_name, phone=phone, slug=slug
        )

    # Check if owner with email or slug already exists
    if crud.get_owner_by_email(db, email):
        return request.state.jinja_env.get_template("signup.html").render(
            request=request,
            error=request.state.gettext("Email already registered."),
            name=name, email=email, business_name=business_name, phone=phone, slug=slug
        )
    if crud.get_owner_by_slug(db, slug):
        return request.state.jinja_env.get_template("signup.html").render(
            request=request,
            error=request.state.gettext("Booking page URL (slug) already taken."),
            name=name, email=email, business_name=business_name, phone=phone, slug=slug
        )

    try:
        owner = schemas.OwnerCreate(
            name=name,
            email=email,
            password=password,
            business_name=business_name,
            phone=phone,
            slug=slug,
            services_json="[]", # Default empty services
            availability_json="{}" # Default empty availability
        )
        crud.create_owner(db=db, owner=owner)
        response = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
        response.set_cookie(key="message", value=request.state.gettext("Registration successful! Please log in."))
        return response
    except Exception as e:
        logger.error(f"Signup error: {e}")
        return request.state.jinja_env.get_template("signup.html").render(
            request=request,
            error=request.state.gettext("An unexpected error occurred during registration."),
            name=name, email=email, business_name=business_name, phone=phone, slug=slug
        )

# --- Login Page ---
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    message = request.cookies.get("message")
    response = request.state.jinja_env.get_template("login.html").render(request=request, message=message)
    res = Response(content=response, media_type="text/html")
    if message:
        res.delete_cookie(key="message")
    return res

@app.post("/token")
async def login_for_access_token(request: Request, db: Session = Depends(get_db), form_data: OAuth2PasswordRequestForm = Depends()):
    owner = crud.authenticate_owner(db, form_data.username, form_data.password)
    if not owner:
        return request.state.jinja_env.get_template("login.html").render(
            request=request,
            error=request.state.gettext("Incorrect email or password")
        )

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": owner.id}, expires_delta=access_token_expires
    )
    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    response.set_cookie(key="access_token", value=f"Bearer {access_token}", httponly=True, samesite="Lax")
    return response

# --- Dashboard ---
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, current_owner: models.Owner = Depends(get_current_owner), db: Session = Depends(get_db)):
    bookings = crud.get_owner_bookings(db, current_owner.id)
    # Convert bookings to a more display-friendly format if needed
    display_bookings = []
    for booking in bookings:
        service_name = "Unknown Service"
        try:
            services = json.loads(current_owner.services_json)
            for service in services:
                if service.get("name") == booking.service_name: # Assuming service_name is stored
                    service_name = service.get("name")
                    break
        except json.JSONDecodeError:
            logger.warning(f"Could not parse services_json for owner {current_owner.id}")

        display_bookings.append({
            "customer_name": booking.customer_name,
            "customer_email": booking.customer_email,
            "customer_phone": booking.customer_phone,
            "service_name": service_name,
            "booking_date": booking.booking_date.strftime("%Y-%m-%d"),
            "booking_time": booking.booking_time.strftime("%H:%M"),
            "status": booking.status
        })

    return request.state.jinja_env.get_template("dashboard.html").render(
        request=request,
        owner=current_owner,
        bookings=display_bookings,
        services=json.loads(current_owner.services_json),
        availability=json.loads(current_owner.availability_json),
        booking_page_url=f"/book/{current_owner.slug}"
    )

@app.post("/dashboard/update_profile", response_class=HTMLResponse)
async def update_owner_profile(request: Request, current_owner: models.Owner = Depends(get_current_owner), db: Session = Depends(get_db)):
    form = await request.form()
    name = form.get("name")
    business_name = form.get("business_name")
    phone = form.get("phone")
    services_json_str = form.get("services_json", "[]")
    availability_json_str = form.get("availability_json", "{}")

    try:
        # Validate services and availability JSON
        services = json.loads(services_json_str)
        availability = json.loads(availability_json_str)

        # Basic validation for services (e.g., must be a list of dicts with 'name', 'duration', 'price')
        if not isinstance(services, list) or not all(isinstance(s, dict) and "name" in s and "duration" in s and "price" in s for s in services):
            raise ValueError("Invalid services format.")
        # Basic validation for availability (e.g., must be a dict)
        if not isinstance(availability, dict):
             raise ValueError("Invalid availability format.")

        owner_update = schemas.OwnerProfileUpdate(
            name=name,
            business_name=business_name,
            phone=phone,
        )
        updated_owner = crud.update_owner_profile(db, current_owner, owner_update)
        updated_owner.services_json = services_json_str
        updated_owner.availability_json = availability_json_str
        db.add(updated_owner)
        db.commit()
        db.refresh(updated_owner)

        response = RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
        response.set_cookie(key="message", value=request.state.gettext("Profile updated successfully!"))
        return response

    except json.JSONDecodeError:
        logger.error(f"JSON decode error for owner {current_owner.id} during profile update.")
        return request.state.jinja_env.get_template("dashboard.html").render(
            request=request,
            owner=current_owner,
            bookings=crud.get_owner_bookings(db, current_owner.id), # Re-fetch bookings
            services=json.loads(current_owner.services_json),
            availability=json.loads(current_owner.availability_json),
            booking_page_url=f"/book/{current_owner.slug}",
            error=request.state.gettext("Invalid JSON format for services or availability.")
        )
    except ValueError as ve:
        logger.error(f"Validation error for owner {current_owner.id} during profile update: {ve}")
        return request.state.jinja_env.get_template("dashboard.html").render(
            request=request,
            owner=current_owner,
            bookings=crud.get_owner_bookings(db, current_owner.id), # Re-fetch bookings
            services=json.loads(current_owner.services_json),
            availability=json.loads(current_owner.availability_json),
            booking_page_url=f"/book/{current_owner.slug}",
            error=request.state.gettext(str(ve))
        )
    except Exception as e:
        logger.error(f"Unexpected error during profile update for owner {current_owner.id}: {e}")
        return request.state.jinja_env.get_template("dashboard.html").render(
            request=request,
            owner=current_owner,
            bookings=crud.get_owner_bookings(db, current_owner.id), # Re-fetch bookings
            services=json.loads(current_owner.services_json),
            availability=json.loads(current_owner.availability_json),
            booking_page_url=f"/book/{current_owner.slug}",
            error=request.state.gettext("An unexpected error occurred during profile update.")
        )


# --- Public Booking Page ---
@app.get("/book/{owner_slug}", response_class=HTMLResponse)
async def booking_page(request: Request, owner_slug: str, db: Session = Depends(get_db)):
    owner = crud.get_owner_by_slug(db, owner_slug)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=request.state.gettext("Booking page not found."))

    services = json.loads(owner.services_json)
    availability = json.loads(owner.availability_json)

    return request.state.jinja_env.get_template("booking_page.html").render(
        request=request,
        owner=owner,
        services=services,
        availability=availability,
        current_date=datetime.now().strftime("%Y-%m-%d")
    )

@app.post("/book/{owner_slug}", response_class=HTMLResponse)
async def submit_booking(request: Request, owner_slug: str, db: Session = Depends(get_db)):
    owner = crud.get_owner_by_slug(db, owner_slug)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=request.state.gettext("Booking page not found."))

    form = await request.form()
    customer_name = form.get("customer_name")
    customer_email = form.get("customer_email")
    customer_phone = form.get("customer_phone")
    service_name = form.get("service")
    booking_date_str = form.get("booking_date")
    booking_time_str = form.get("booking_time")

    try:
        booking_date = datetime.strptime(booking_date_str, "%Y-%m-%d").date()
        booking_time = datetime.strptime(booking_time_str, "%H:%M").time()
    except (ValueError, TypeError):
        return request.state.jinja_env.get_template("booking_page.html").render(
            request=request,
            owner=owner,
            services=json.loads(owner.services_json),
            availability=json.loads(owner.availability_json),
            current_date=datetime.now().strftime("%Y-%m-%d"),
            error=request.state.gettext("Invalid date or time format.")
        )

    # Basic validation
    if not all([customer_name, customer_email, customer_phone, service_name, booking_date_str, booking_time_str]):
        return request.state.jinja_env.get_template("booking_page.html").render(
            request=request,
            owner=owner,
            services=json.loads(owner.services_json),
            availability=json.loads(owner.availability_json),
            current_date=datetime.now().strftime("%Y-%m-%d"),
            error=request.state.gettext("All fields are required.")
        )

    # Check for service existence and duration for availability check
    selected_service = next((s for s in json.loads(owner.services_json) if s["name"] == service_name), None)
    if not selected_service:
        return request.state.jinja_env.get_template("booking_page.html").render(
            request=request,
            owner=owner,
            services=json.loads(owner.services_json),
            availability=json.loads(owner.availability_json),
            current_date=datetime.now().strftime("%Y-%m-%d"),
            error=request.state.gettext("Selected service is not valid.")
        )
    
    # TODO: Implement actual availability check based on owner.availability_json and service duration
    # This would involve parsing availability, checking if the chosen slot is open,
    # and ensuring no overlaps with existing bookings for the owner.
    # For MVP, we assume the selected time slot is valid if it comes from the UI.

    booking = schemas.BookingCreate(
        customer_name=customer_name,
        customer_email=customer_email,
        customer_phone=customer_phone,
        service_name=service_name,
        booking_date=booking_date,
        booking_time=booking_time,
        status="pending"
    )

    try:
        db_booking = crud.create_booking(db=db, booking=booking, owner_id=owner.id)

        # Send notifications
        notifications.send_owner_notification(owner, db_booking)
        notifications.send_customer_confirmation(owner, db_booking)

        return request.state.jinja_env.get_template("booking_confirmation.html").render(
            request=request,
            owner=owner,
            booking=db_booking,
            customer_name=customer_name,
            service_name=service_name,
            booking_date=booking_date.strftime("%Y-%m-%d"),
            booking_time=booking_time.strftime("%H:%M")
        )
    except Exception as e:
        logger.error(f"Booking submission error: {e}")
        return request.state.jinja_env.get_template("booking_page.html").render(
            request=request,
            owner=owner,
            services=json.loads(owner.services_json),
            availability=json.loads(owner.availability_json),
            current_date=datetime.now().strftime("%Y-%m-%d"),
            error=request.state.gettext("An unexpected error occurred during booking. Please try again.")
        )

# --- Logout ---
@app.get("/logout", response_class=RedirectResponse, status_code=status.HTTP_302_FOUND)
async def logout():
    response = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    response.delete_cookie(key="access_token")
    return response

# --- Language Toggle Endpoint ---
@app.get("/lang/{lang_code}", response_class=RedirectResponse)
async def set_language(request: Request, lang_code: str):
    # Determine the redirect URL based on the Referer header or a default
    referer = request.headers.get("referer", "/")
    response = RedirectResponse(url=referer, status_code=status.HTTP_302_FOUND)
    response.set_cookie(key="lang", value=lang_code, httponly=False, samesite="Lax")
    return response
