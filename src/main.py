from fastapi import FastAPI, Depends, HTTPException, status, Request, Form, Response
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, date
import json
import logging

from . import crud, models, schemas, security, notifications
from .database import SessionLocal, engine, create_tables, get_db
from .config import settings
from .i18n_config import get_jinja_env # Import get_jinja_env
from typing import Optional, List, Dict

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create database tables on startup (will be called by app.on_event("startup"))

app = FastAPI()

# Initialize Jinja2Templates with the custom environment
# This will be overridden in tests to control locale
templates = Jinja2Templates(directory=settings.PROJECT_ROOT + "/templates")

@app.middleware("http")
async def add_language_middleware(request: Request, call_next):
    lang = request.query_params.get("lang", "en") # Default to English
    request.state.lang = lang
    request.state.jinja_env = get_jinja_env(locale=lang) # Get a locale-specific Jinja environment
    
    response = await call_next(request)
    return response

# Dependency to get the current owner from the JWT token
def get_current_owner(db: Session = Depends(get_db), token: str = Depends(security.oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = security.decode_access_token(token)
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
        token_data = schemas.TokenData(email=email)
    except Exception as e:
        logger.error(f"Token decoding error: {e}")
        raise credentials_exception
    owner = crud.get_owner_by_email(db, email=token_data.email)
    if owner is None:
        raise credentials_exception
    return owner

# --- Routes ---

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.post("/signup", response_model=schemas.Token)
def signup_owner(owner: schemas.OwnerCreate, db: Session = Depends(get_db)):
    db_owner = crud.get_owner_by_email(db, email=owner.email)
    if db_owner:
        raise HTTPException(status_code=400, detail="Email already registered")
    db_owner = crud.get_owner_by_slug(db, slug=owner.slug)
    if db_owner:
        raise HTTPException(status_code=400, detail="Business slug already taken")
    
    db_owner = crud.create_owner(db=db, owner=owner)
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": db_owner.email}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/token", response_model=schemas.Token)
def login_for_access_token(response: Response, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    owner = crud.authenticate_owner(db, form_data.username, form_data.password)
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
    response.set_cookie(key="access_token", value=access_token, httponly=True, samesite="Lax")
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    env = request.state.jinja_env if hasattr(request.state, 'jinja_env') else get_jinja_env()
    return HTMLResponse(env.get_template("login.html").render(request=request))

@app.post("/login", response_class=RedirectResponse)
async def handle_login(request: Request, response: Response, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    try:
        token_response = login_for_access_token(response, form_data, db)
        access_token = token_response["access_token"]
        response.set_cookie(key="access_token", value=access_token, httponly=True, samesite="Lax")
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    except HTTPException as e:
        env = request.state.jinja_env if hasattr(request.state, 'jinja_env') else get_jinja_env()
        # Re-render login page with error
        return HTMLResponse(env.get_template("login.html").render(
            request=request,
            error=e.detail
        ), status_code=e.status_code)

@app.get("/logout", response_class=RedirectResponse)
async def logout(response: Response):
    response.delete_cookie(key="access_token")
    return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)


@app.get("/dashboard", response_class=HTMLResponse)
async def read_dashboard(request: Request, db: Session = Depends(get_db), current_owner: models.Owner = Depends(get_current_owner)):
    bookings = crud.get_owner_bookings(db, owner_id=current_owner.id)
    # Filter for upcoming bookings (today or in the future)
    today = date.today()
    upcoming_bookings = [
        b for b in bookings
        if datetime.strptime(b.booking_date, "%Y-%m-%d").date() >= today
    ]
    upcoming_bookings.sort(key=lambda b: (b.booking_date, b.booking_time)) # Ensure sorted

    owner_services = json.loads(current_owner.services_json) if current_owner.services_json else []
    owner_availability = json.loads(current_owner.availability_json) if current_owner.availability_json else {}

    env = request.state.jinja_env if hasattr(request.state, 'jinja_env') else get_jinja_env()
    return HTMLResponse(env.get_template("dashboard.html").render(
        request=request,
        owner=current_owner,
        bookings=upcoming_bookings,
        services=owner_services,
        availability=owner_availability
    ))

@app.post("/dashboard/profile", response_class=RedirectResponse)
async def update_owner_profile_route(
    request: Request,
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(get_current_owner),
    name: str = Form(...),
    business_name: str = Form(...),
    phone: str = Form(...),
    services_json: str = Form("[]"),
    availability_json: str = Form("{}")
):
    try:
        owner_update = schemas.OwnerProfileUpdate(
            name=name,
            business_name=business_name,
            phone=phone,
            services_json=services_json, # Handled directly
            availability_json=availability_json # Handled directly
        )
        
        # Validate JSON content
        try:
            parsed_services = json.loads(services_json)
            # Basic validation for services structure
            if not isinstance(parsed_services, list) or not all(isinstance(s, dict) and "name" in s and "duration" in s for s in parsed_services):
                raise ValueError("Services JSON is malformed.")
            current_owner.services_json = services_json
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Services JSON is invalid.")
        except ValueError as ve:
            raise HTTPException(status_code=400, detail=str(ve))

        try:
            parsed_availability = json.loads(availability_json)
            # Basic validation for availability structure
            if not isinstance(parsed_availability, dict):
                raise ValueError("Availability JSON is malformed.")
            current_owner.availability_json = availability_json
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Availability JSON is invalid.")
        except ValueError as ve:
            raise HTTPException(status_code=400, detail=str(ve))

        crud.update_owner_profile(db, current_owner, owner_update)
        return RedirectResponse(url="/dashboard?status=profile_updated", status_code=status.HTTP_302_FOUND)
    except HTTPException as e:
        # If there's an HTTP exception, redirect back with an error
        return RedirectResponse(url=f"/dashboard?error={e.detail}", status_code=status.HTTP_302_FOUND)
    except Exception as e:
        logger.exception("Error updating profile:")
        return RedirectResponse(url=f"/dashboard?error=An unexpected error occurred: {e}", status_code=status.HTTP_302_FOUND)


@app.get("/bookslot/{owner_slug}", response_class=HTMLResponse)
async def public_booking_page(request: Request, owner_slug: str, db: Session = Depends(get_db)):
    owner = crud.get_owner_by_slug(db, slug=owner_slug)
    if not owner:
        raise HTTPException(status_code=404, detail="Business not found")

    services = json.loads(owner.services_json) if owner.services_json else []
    availability = json.loads(owner.availability_json) if owner.availability_json else {}

    env = request.state.jinja_env if hasattr(request.state, 'jinja_env') else get_jinja_env()
    return HTMLResponse(env.get_template("booking_page.html").render(
        request=request,
        owner=owner,
        services=services,
        availability=availability,
        error=request.query_params.get("error")
    ))

@app.post("/bookslot/{owner_slug}", response_class=HTMLResponse)
async def submit_booking(
    request: Request,
    owner_slug: str,
    db: Session = Depends(get_db),
    customer_name: str = Form(...),
    customer_email: str = Form(...),
    customer_phone: str = Form(...),
    service_name: str = Form(...),
    booking_date: str = Form(...),
    booking_time: str = Form(...),
    notes: Optional[str] = Form(None)
):
    owner = crud.get_owner_by_slug(db, slug=owner_slug)
    if not owner:
        raise HTTPException(status_code=404, detail="Business not found")

    services = json.loads(owner.services_json)
    if not any(s["name"] == service_name for s in services):
        return HTMLResponse(request.state.jinja_env.get_template("booking_page.html").render(
            request=request, owner=owner, services=services, availability=json.loads(owner.availability_json),
            error=request.state.jinja_env.gettext("Invalid service selected.")
        ), status_code=400)

    try:
        booking_data = schemas.BookingCreate(
            customer_name=customer_name,
            customer_email=customer_email,
            customer_phone=customer_phone,
            service_name=service_name,
            booking_date=booking_date,
            booking_time=booking_time,
            notes=notes
        )
        db_booking = crud.create_booking(db=db, booking=booking_data, owner_id=owner.id)

        # Send notifications
        notifications.send_email(
            to_email=customer_email,
            subject=request.state.jinja_env.gettext("Booking Confirmation"),
            template_name="email_booking_confirmation_customer.html",
            template_data={"owner": owner, "booking": db_booking, "lang": request.state.lang}
        )
        notifications.send_email(
            to_email=owner.email,
            subject=request.state.jinja_env.gettext("New Booking Received"),
            template_name="email_booking_notification_owner.html",
            template_data={"owner": owner, "booking": db_booking, "lang": request.state.lang}
        )
        if owner.phone and settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN:
            notifications.send_whatsapp_message(
                to_phone_number=owner.phone,
                message=request.state.jinja_env.gettext(f"New booking for {service_name} on {booking_date} at {booking_time} by {customer_name}. Customer Phone: {customer_phone}"),
                lang=request.state.lang
            )
        
        env = request.state.jinja_env if hasattr(request.state, 'jinja_env') else get_jinja_env()
        return HTMLResponse(env.get_template("booking_confirmation.html").render(
            request=request, owner=owner, booking=db_booking
        ))
    except Exception as e:
        logger.exception("Error submitting booking:")
        env = request.state.jinja_env if hasattr(request.state, 'jinja_env') else get_jinja_env()
        return HTMLResponse(env.get_template("booking_page.html").render(
            request=request, owner=owner, services=services, availability=json.loads(owner.availability_json),
            error=request.state.jinja_env.gettext(f"An error occurred: {e}")
        ), status_code=500)

# Make sure Jinja2 templates can access gettext functions
@app.on_event("startup")
async def startup_event():
    logger.info("Application startup event: creating database tables.")
    create_tables()

    pass # Middleware handles language specific env setup