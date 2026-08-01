from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy.orm import Session
from . import models, schemas, crud, security, notifications
from .database import engine, get_db, create_tables, Base
from .config import settings
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.requests import Request
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from datetime import timedelta
from typing import List, Dict, Any
import json
import logging
from src.i18n_config import get_jinja_env
from gettext import gettext as _
import os
from urllib.parse import urlencode

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# OAuth2PasswordBearer for token authentication
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Dependency to get the current owner
async def get_current_owner(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
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
    except Exception:
        raise credentials_exception
    owner = crud.get_owner_by_email(db, email=token_data.email)
    if owner is None:
        raise credentials_exception
    return owner

# Dependency to get the current active owner (ensures owner is logged in)
def get_current_active_owner(current_owner: models.Owner = Depends(get_current_owner)):
    return current_owner

@app.on_event("startup")
async def startup_event():
    # Only create tables if not in testing mode, as tests will manage their own DB
    if not settings.TESTING:
        create_tables()
    logger.info(f"Application started. Testing mode: {settings.TESTING}")

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.post("/token", response_model=schemas.Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
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

@app.post("/signup", response_model=schemas.Owner)
def create_owner_signup(owner: schemas.OwnerCreate, db: Session = Depends(get_db)):
    db_owner = crud.get_owner_by_email(db, email=owner.email)
    if db_owner:
        raise HTTPException(status_code=400, detail="Email already registered")
    # Basic slug generation from business name, can be refined
    if not owner.slug:
        owner.slug = owner.business_name.lower().replace(" ", "-")
    db_owner = crud.create_owner(db=db, owner=owner)
    return db_owner

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db), current_owner: models.Owner = Depends(get_current_active_owner)):
    locale = request.query_params.get('lang', 'en')
    env = get_jinja_env(locale)
    template = env.get_template("dashboard.html")

    bookings = crud.get_owner_bookings(db, current_owner.id)
    
    # Process services and availability for display/editing
    services = json.loads(current_owner.services_json) if current_owner.services_json else []
    availability = json.loads(current_owner.availability_json) if current_owner.availability_json else {}

    return template.render(
        request=request,
        owner=current_owner,
        bookings=bookings,
        services=services,
        availability=availability,
        locale=locale,
        _=_ # Pass gettext function to template
    )

@app.post("/dashboard/profile", response_model=schemas.Owner)
async def update_owner_profile(
    request: Request,
    owner_update: schemas.OwnerProfileUpdate = Depends(schemas.OwnerProfileUpdate.as_form),
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(get_current_active_owner)
):
    try:
        # Update basic profile info
        crud.update_owner_profile(db, current_owner, owner_update)

        # Handle services (JSON string)
        if owner_update.services:
            current_owner.services_json = json.dumps([s.dict() for s in owner_update.services])
        else:
            current_owner.services_json = "[]"

        # Handle availability (JSON string)
        if owner_update.availability:
            current_owner.availability_json = json.dumps(owner_update.availability.dict())
        else:
            current_owner.availability_json = "{}"
        
        db.add(current_owner)
        db.commit()
        db.refresh(current_owner)
        return current_owner
    except Exception as e:
        logger.error(f"Error updating owner profile: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update profile: {e}")

@app.get("/{owner_slug}", response_class=HTMLResponse)
async def booking_page(owner_slug: str, request: Request, db: Session = Depends(get_db)):
    owner = crud.get_owner_by_slug(db, owner_slug)
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")

    locale = request.query_params.get('lang', 'en')
    env = get_jinja_env(locale)
    template = env.get_template("booking_page.html")

    services = json.loads(owner.services_json) if owner.services_json else []
    availability = json.loads(owner.availability_json) if owner.availability_json else {}

    return template.render(
        request=request,
        owner=owner,
        services=services,
        availability=availability,
        locale=locale,
        _=_ # Pass gettext function to template
    )

@app.post("/{owner_slug}/book", response_class=HTMLResponse)
async def submit_booking(
    owner_slug: str,
    request: Request,
    db: Session = Depends(get_db)
):
    owner = crud.get_owner_by_slug(db, owner_slug)
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")

    locale = request.query_params.get('lang', 'en')
    env = get_jinja_env(locale)

    try:
        form = await request.form()
        booking_data = schemas.BookingCreate(
            customer_name=form.get("customer_name"),
            customer_email=form.get("customer_email"),
            customer_phone=form.get("customer_phone"),
            service_name=form.get("service_name"),
            booking_date=form.get("booking_date"),
            booking_time=form.get("booking_time"),
            notes=form.get("notes", "")
        )
        
        db_booking = crud.create_booking(db=db, booking=booking_data, owner_id=owner.id)

        # Send notifications
        notifications.send_booking_confirmation_email(owner, booking_data)
        notifications.send_owner_notification_email(owner, booking_data)
        notifications.send_owner_notification_whatsapp(owner, booking_data)

        confirmation_template = env.get_template("booking_confirmation.html")
        return confirmation_template.render(
            request=request,
            owner=owner,
            booking=db_booking,
            locale=locale,
            _=_
        )

    except Exception as e:
        logger.error(f"Error submitting booking: {e}")
        error_template = env.get_template("booking_page.html") # Render the booking page again with an error message
        services = json.loads(owner.services_json) if owner.services_json else []
        availability = json.loads(owner.availability_json) if owner.availability_json else {}
        return error_template.render(
            request=request,
            owner=owner,
            services=services,
            availability=availability,
            locale=locale,
            error_message=_("Failed to submit booking. Please try again."),
            _=_
        )

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    locale = request.query_params.get('lang', 'en')
    env = get_jinja_env(locale)
    template = env.get_template("login.html")
    return template.render(request=request, locale=locale, _=_)

@app.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request):
    locale = request.query_params.get('lang', 'en')
    env = get_jinja_env(locale)
    template = env.get_template("signup.html")
    return template.render(request=request, locale=locale, _=_)

@app.get("/")
async def root_redirect():
    return RedirectResponse(url="/docs") # Or a marketing landing page
