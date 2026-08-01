from fastapi import FastAPI, Depends, HTTPException, status, Request, Form, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from sqlalchemy.orm import Session
from datetime import timedelta, datetime, date, time
import json
import gettext
import os
import logging
from typing import Optional, List
from jinja2 import Environment # Import Environment for type hinting

from . import models, schemas, crud, security, notifications
from .database import SessionLocal, engine, Base, get_db
from .config import settings
from .i18n_config import get_jinja_env

logger = logging.getLogger(__name__)

app = FastAPI()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Create database tables on startup
@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    if settings.TESTING:
        logger.info("Running in testing mode, tables created.")

# Dependency for getting the Jinja2 environment with i18n
def get_jinja_env_dependency(request: Request):
    locale = request.cookies.get("lang", "en")
    return get_jinja_env(locale)

# Dependency to get current owner from token
async def get_current_owner(request: Request, db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
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
    except Exception: # JWTError or other decoding issues
        raise credentials_exception
    owner = crud.get_owner_by_email(db, email=token_data.email)
    if owner is None:
        raise credentials_exception
    return owner

# --- API Endpoints (for backend interaction, e.g., by frontend JS or for token generation) ---

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

@app.post("/owner/signup", response_model=schemas.Token)
async def signup_owner(owner: schemas.OwnerCreate, db: Session = Depends(get_db)):
    db_owner = crud.get_owner_by_email(db, email=owner.email)
    if db_owner:
        raise HTTPException(status_code=400, detail="Email already registered")
    if not owner.slug:
        owner.slug = owner.business_name.lower().replace(" ", "-")
    db_owner = crud.create_owner(db=db, owner=owner)
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": db_owner.email}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer", "owner": schemas.Owner.from_orm(db_owner)}

# --- HTML Endpoints (for rendering pages) ---

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request, jinja_env: Environment = Depends(get_jinja_env_dependency)):
    template = jinja_env.get_template("index.html")
    return template.render(request=request) # index.html might have login/signup links

@app.get("/health", response_class=HTMLResponse)
async def health():
    return "OK"

@app.get("/owner/register", response_class=HTMLResponse)
async def register_page(request: Request, jinja_env: Environment = Depends(get_jinja_env_dependency)):
    template = jinja_env.get_template("signup.html")
    return template.render(request=request)

@app.get("/owner/login", response_class=HTMLResponse)
async def login_page(request: Request, jinja_env: Environment = Depends(get_jinja_env_dependency)):
    template = jinja_env.get_template("login.html")
    return template.render(request=request)

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db),
                    current_owner: models.Owner = Depends(get_current_owner),
                    jinja_env: Environment = Depends(get_jinja_env_dependency)):
    owner_bookings = crud.get_owner_bookings(db, current_owner.id)
    
    # Parse services and availability from JSON strings
    services = json.loads(current_owner.services_json) if current_owner.services_json else []
    availability = json.loads(current_owner.availability_json) if current_owner.availability_json else {}

    template = jinja_env.get_template("dashboard.html")
    return template.render(
        request=request,
        owner=current_owner,
        bookings=owner_bookings,
        services=services,
        availability=availability,
        messages=[] # For displaying success/error messages
    )

@app.post("/dashboard", response_class=HTMLResponse)
async def update_profile(
    request: Request,
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(get_current_owner),
    jinja_env: Environment = Depends(get_jinja_env_dependency),
    name: str = Form(...),
    business_name: str = Form(...),
    phone: str = Form(...),
    services_json: str = Form("[]"), # Expecting JSON string
    availability_json: str = Form("{}") # Expecting JSON string
):
    messages = []
    try:
        # Validate JSON inputs
        try:
            validated_services = [schemas.Service(**s) for s in json.loads(services_json)]
            current_owner.services_json = json.dumps([s.dict() for s in validated_services])
        except (json.JSONDecodeError, ValueError) as e:
            messages.append({"type": "error", "content": f"Invalid services format: {e}"})
            raise HTTPException(status_code=400, detail="Invalid services JSON format")

        try:
            validated_availability = schemas.Availability(**json.loads(availability_json))
            current_owner.availability_json = json.dumps(validated_availability.dict())
        except (json.JSONDecodeError, ValueError) as e:
            messages.append({"type": "error", "content": f"Invalid availability format: {e}"})
            raise HTTPException(status_code=400, detail="Invalid availability JSON format")

        owner_update = schemas.OwnerProfileUpdate(
            name=name,
            business_name=business_name,
            phone=phone,
            services_json=current_owner.services_json, # Use the validated JSON
            availability_json=current_owner.availability_json # Use the validated JSON
        )
        crud.update_owner_profile(db, current_owner, owner_update)
        messages.append({"type": "success", "content": jinja_env.gettext("Profile updated successfully!")})

    except HTTPException as e:
        messages.append({"type": "error", "content": e.detail})
    except Exception as e:
        logger.error(f"Error updating profile: {e}")
        messages.append({"type": "error", "content": jinja_env.gettext("An unexpected error occurred.")})

    owner_bookings = crud.get_owner_bookings(db, current_owner.id)
    template = jinja_env.get_template("dashboard.html")
    return template.render(
        request=request,
        owner=current_owner,
        bookings=owner_bookings,
        services=json.loads(current_owner.services_json),
        availability=json.loads(current_owner.availability_json),
        messages=messages
    )

@app.get("/book/{owner_slug}", response_class=HTMLResponse)
async def public_booking_page(
    owner_slug: str,
    request: Request,
    db: Session = Depends(get_db),
    jinja_env: Environment = Depends(get_jinja_env_dependency)
):
    owner = crud.get_owner_by_slug(db, owner_slug)
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")

    services = json.loads(owner.services_json) if owner.services_json else []
    availability = json.loads(owner.availability_json) if owner.availability_json else {}

    template = jinja_env.get_template("booking_page.html")
    return template.render(
        request=request,
        owner=owner,
        services=services,
        availability=availability,
        messages=[]
    )

@app.post("/book/{owner_slug}", response_class=HTMLResponse)
async def submit_booking(
    owner_slug: str,
    request: Request,
    db: Session = Depends(get_db),
    jinja_env: Environment = Depends(get_jinja_env_dependency),
    customer_name: str = Form(...),
    customer_email: str = Form(...),
    customer_phone: str = Form(...),
    service_name: str = Form(...),
    booking_date: date = Form(...),
    booking_time: time = Form(...)
):
    messages = []
    owner = crud.get_owner_by_slug(db, owner_slug)
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")

    services = json.loads(owner.services_json) if owner.services_json else []
    availability = json.loads(owner.availability_json) if owner.availability_json else {}

    # Basic validation for service and availability (more complex logic might be needed)
    selected_service = next((s for s in services if s['name'] == service_name), None)
    if not selected_service:
        messages.append({"type": "error", "content": jinja_env.gettext("Selected service is not valid.")})
    
    day_of_week = booking_date.strftime('%A').lower() # e.g., "monday"
    if day_of_week not in availability or not availability[day_of_week]['is_available']:
        messages.append({"type": "error", "content": jinja_env.gettext("Booking date is not available.")})
    else:
        start_time_str = availability[day_of_week]['start_time']
        end_time_str = availability[day_of_week]['end_time']
        
        try:
            available_start = datetime.strptime(start_time_str, "%H:%M").time()
            available_end = datetime.strptime(end_time_str, "%H:%M").time()
            if not (available_start <= booking_time < available_end):
                messages.append({"type": "error", "content": jinja_env.gettext("Selected time is outside of available hours.")})
        except ValueError:
            messages.append({"type": "error", "content": jinja_env.gettext("Invalid availability time format for owner.")})


    if messages:
        template = jinja_env.get_template("booking_page.html")
        return template.render(
            request=request,
            owner=owner,
            services=services,
            availability=availability,
            messages=messages
        )

    try:
        booking_data = schemas.BookingCreate(
            customer_name=customer_name,
            customer_email=customer_email,
            customer_phone=customer_phone,
            service_name=service_name,
            booking_date=booking_date,
            booking_time=booking_time,
            status="pending"
        )
        db_booking = crud.create_booking(db, booking_data, owner.id)

        # Send notifications
        notifications.send_booking_confirmation_email(owner, db_booking, selected_service)
        notifications.send_owner_notification(owner, db_booking, selected_service)
        
        return RedirectResponse(url=f"/booking_confirmation/{owner_slug}", status_code=status.HTTP_303_SEE_OTHER)

    except Exception as e:
        logger.error(f"Error submitting booking: {e}")
        messages.append({"type": "error", "content": jinja_env.gettext("An unexpected error occurred during booking.")})
        template = jinja_env.get_template("booking_page.html")
        return template.render(
            request=request,
            owner=owner,
            services=services,
            availability=availability,
            messages=messages
        )

@app.get("/booking_confirmation/{owner_slug}", response_class=HTMLResponse)
async def booking_confirmation_page(
    owner_slug: str,
    request: Request,
    db: Session = Depends(get_db),
    jinja_env: Environment = Depends(get_jinja_env_dependency)
):
    owner = crud.get_owner_by_slug(db, owner_slug)
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")

    template = jinja_env.get_template("booking_confirmation.html")
    return template.render(request=request, owner=owner)

@app.get("/logout", response_class=RedirectResponse)
async def logout():
    response = RedirectResponse(url="/owner/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie("access_token") # Or whatever cookie stores the token
    return response

@app.get("/set_language/{lang_code}", response_class=RedirectResponse)
async def set_language(lang_code: str, request: Request):
    response = RedirectResponse(url=request.headers.get("referer", "/"), status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(key="lang", value=lang_code, httponly=False, expires=3600*24*30) # Expires in 30 days
    return response

# Error handlers for HTML pages
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    jinja_env = get_jinja_env(request.cookies.get("lang", "en")) # Get env dynamically here
    if exc.status_code == 404:
        template = jinja_env.get_template("404.html")
        return HTMLResponse(template.render(request=request, message=exc.detail), status_code=exc.status_code)
    if exc.status_code == 401:
        # For 401, redirect to login page for HTML requests
        if request.url.path.startswith("/dashboard"): # Only redirect if trying to access protected HTML route
            response = RedirectResponse(url="/owner/login")
            response.delete_cookie("access_token") # Clear potentially invalid token
            return response
        # For API 401, let FastAPI handle JSON response, for HTML show error page
        return HTMLResponse(jinja_env.get_template("error.html").render(request=request, message=exc.detail), status_code=exc.status_code)
    
    template = jinja_env.get_template("error.html")
    return HTMLResponse(template.render(request=request, message=exc.detail), status_code=exc.status_code)
