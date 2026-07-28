from fastapi import FastAPI, Depends, HTTPException, status, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta
from typing import List, Dict, Any
import json
import os
import gettext

from . import models, schemas, crud, security
from .database import SessionLocal, engine, Base
from .config import settings
from .notifications import send_booking_confirmation_email, send_owner_notification_email, send_whatsapp_notification
from .i18n_config import get_jinja_env

# Create database tables
# This is suitable for development/initial setup. For production, Alembic migrations are recommended.
Base.metadata.create_all(bind=engine)

app = FastAPI()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Helper for i18n
def get_locale_from_request(request: Request) -> str:
    lang = request.query_params.get("lang", request.cookies.get("lang", "en"))
    if lang not in ["en", "ar", "fr"]:
        lang = "en"
    return lang

# --- Authentication Endpoints ---
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
    db_owner = crud.get_owner_by_slug(db, slug=owner.slug)
    if db_owner:
        raise HTTPException(status_code=400, detail="Slug already taken")
    return crud.create_owner(db=db, owner=owner)

# --- Owner Dashboard Endpoints ---
@app.get("/dashboard", response_class=HTMLResponse)
async def owner_dashboard(request: Request, db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    current_owner = security.get_current_owner(db, token)
    if not current_owner:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    lang = get_locale_from_request(request)
    env = get_jinja_env(lang)
    _ = env.gettext

    try:
        upcoming_bookings = db.query(models.Booking).filter(models.Booking.owner_id == current_owner.id).order_by(models.Booking.booking_time).all()
        services = json.loads(current_owner.services_json) if current_owner.services_json else []
        availability = json.loads(current_owner.availability_json) if current_owner.availability_json else {}

        response = HTMLResponse(env.get_template("dashboard.html").render(
            request=request,
            owner=current_owner,
            upcoming_bookings=upcoming_bookings,
            services=services,
            availability=availability,
            lang=lang,
            _=_,
            current_url=str(request.url) # Pass current URL for language toggle
        ))
        response.set_cookie(key="lang", value=lang, httponly=True)
        return response
    except Exception as e:
        print(f"Error rendering dashboard: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/dashboard/profile", response_model=schemas.Owner)
async def update_owner_profile_endpoint(
    owner_update: schemas.OwnerProfileUpdate,
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme)
):
    current_owner = security.get_current_owner(db, token)
    if not current_owner:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    try:
        # Validate services_json and availability_json before updating
        # This is a simplified check; a more robust validation might be needed
        try:
            json.loads(owner_update.services_json)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid services format (must be JSON)")

        try:
            json.loads(owner_update.availability_json)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid availability format (must be JSON)")

        current_owner.services_json = owner_update.services_json
        current_owner.availability_json = owner_update.availability_json

        updated_owner = crud.update_owner_profile(db, current_owner, owner_update)
        return updated_owner
    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"Error updating owner profile: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# --- Public Booking Page Endpoints ---
@app.get("/{owner_slug}", response_class=HTMLResponse)
async def booking_page(owner_slug: str, request: Request, db: Session = Depends(get_db)):
    owner = crud.get_owner_by_slug(db, owner_slug)
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")

    lang = get_locale_from_request(request)
    env = get_jinja_env(lang)
    _ = env.gettext

    services = json.loads(owner.services_json) if owner.services_json else []
    availability = json.loads(owner.availability_json) if owner.availability_json else {}

    response = HTMLResponse(env.get_template("booking_page.html").render(
        request=request,
        owner=owner,
        services=services,
        availability=availability,
        lang=lang,
        _=_,
        current_url=str(request.url) # Pass current URL for language toggle
    ))
    response.set_cookie(key="lang", value=lang, httponly=True)
    return response

@app.post("/{owner_slug}/book", response_class=HTMLResponse)
async def submit_booking(owner_slug: str, request: Request, db: Session = Depends(get_db)):
    owner = crud.get_owner_by_slug(db, owner_slug)
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")

    lang = get_locale_from_request(request)
    env = get_jinja_env(lang)
    _ = env.gettext

    form_data = await request.form()
    try:
        booking_data = schemas.BookingCreate(
            customer_name=form_data["customer_name"],
            customer_email=form_data["customer_email"],
            customer_phone=form_data.get("customer_phone", ""),
            service_name=form_data["service_name"],
            booking_time=form_data["booking_time"],
            status="pending" # Default status
        )
        db_booking = crud.create_booking(db=db, booking=booking_data, owner_id=owner.id)

        # Send notifications
        send_booking_confirmation_email(booking_data, owner.email, owner.business_name)
        send_owner_notification_email(booking_data, owner.email, owner.business_name)
        if owner.phone:
            send_whatsapp_notification(booking_data, owner.phone, owner.business_name)

        return env.get_template("booking_confirmation.html").render(
            request=request,
            booking=db_booking,
            owner=owner,
            lang=lang,
            _=_,
            current_url=str(request.url) # Pass current URL for language toggle
        )
    except Exception as e:
        print(f"Error submitting booking: {e}")
        # Re-render booking page with error message or redirect to an error page
        services = json.loads(owner.services_json) if owner.services_json else []
        availability = json.loads(owner.availability_json) if owner.availability_json else {}
        return env.get_template("booking_page.html").render(
            request=request,
            owner=owner,
            services=services,
            availability=availability,
            lang=lang,
            error_message=_("Failed to submit booking. Please try again."),
            _=_,
            current_url=str(request.url) # Pass current URL for language toggle
        )

# --- Health Check Endpoint ---
@app.get("/health")
def health_check():
    return {"status": "ok"}

# --- Login Page (if needed, otherwise dashboard handles redirect) ---
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    lang = get_locale_from_request(request)
    env = get_jinja_env(lang)
    _ = env.gettext
    response = HTMLResponse(env.get_template("login.html").render(request=request, lang=lang, _=_,
                                                            current_url=str(request.url) # Pass current URL for language toggle
    ))
    response.set_cookie(key="lang", value=lang, httponly=True)
    return response

# Static files (assuming a 'static' folder at project root)
from fastapi.staticfiles import StaticFiles
app.mount("/static", StaticFiles(directory="static"), name="static")
