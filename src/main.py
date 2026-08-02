from fastapi import FastAPI, Depends, HTTPException, status, Request, Form, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import timedelta, date, time, datetime
from typing import List, Dict, Any, Optional
import json
import os
import gettext
import logging

from . import models, schemas, crud, security, notifications
from .database import SessionLocal, engine, get_db, create_tables
from .config import settings
from .i18n_config import get_jinja_env

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Create database tables on startup
create_tables()

app = FastAPI()

# Set up Jinja2 templates using the i18n environment
TEMPLATES_DIR = os.path.join(settings.PROJECT_ROOT, 'templates')

@app.middleware("http")
async def add_i18n_and_templates_to_request(request: Request, call_next):
    lang = request.cookies.get("lang", "en")
    request.state.gettext = gettext.translation('messages', settings.LOCALES_DIR, languages=[lang], fallback=True)
    request.state.gettext.install()
    request.state.templates = get_jinja_env(locale=lang)
    response = await call_next(request)
    return response

@app.get("/health", tags=["Health Check"])
async def health_check():
    return {"status": "ok", "message": "BookSlot API is up and running!"}

@app.post("/token", response_model=schemas.Token, tags=["Auth"])
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

@app.get("/signup", response_class=HTMLResponse, tags=["Auth"])
async def signup_page(request: Request):
    return request.state.templates.get_template("signup.html").render({"request": request})

@app.post("/signup", response_class=HTMLResponse, tags=["Auth"])
async def signup_owner(request: Request, db: Session = Depends(get_db),
                       name: str = Form(...), email: str = Form(...), password: str = Form(...),
                       business_name: str = Form(...), slug: str = Form(...), phone: Optional[str] = Form(None)):
    
    _ = request.state.gettext.gettext

    db_owner = crud.get_owner_by_email(db, email=email)
    if db_owner:
        return request.state.templates.get_template("signup.html").render({"request": request, "error": _("Email already registered")})
    
    db_owner_slug = crud.get_owner_by_slug(db, slug=slug)
    if db_owner_slug:
        return request.state.templates.get_template("signup.html").render({"request": request, "error": _("Business URL already taken")})

    try:
        owner = schemas.OwnerCreate(name=name, email=email, password=password, business_name=business_name, slug=slug, phone=phone)
        crud.create_owner(db=db, owner=owner)
        response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
        return response
    except Exception as e:
        logger.error(f"Signup error: {e}")
        return request.state.templates.get_template("signup.html").render({"request": request, "error": _("An unexpected error occurred during signup.")})

@app.get("/login", response_class=HTMLResponse, tags=["Auth"])
async def login_page(request: Request):
    return request.state.templates.get_template("login.html").render({"request": request})

@app.post("/login", response_class=HTMLResponse, tags=["Auth"])
async def login(request: Request, db: Session = Depends(get_db), email: str = Form(...), password: str = Form(...)):
    _ = request.state.gettext.gettext

    owner = crud.authenticate_owner(db, email, password)
    if not owner:
        return request.state.templates.get_template("login.html").render({"request": request, "error": _("Incorrect email or password")})
    
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": owner.email}, expires_delta=access_token_expires
    )
    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(key="access_token", value=access_token, httponly=True, expires=access_token_expires.total_seconds())
    return response

@app.get("/logout", tags=["Auth"])
async def logout(request: Request):
    response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(key="access_token")
    return response

@app.get("/dashboard", response_class=HTMLResponse, tags=["Owner Dashboard"])
async def owner_dashboard(request: Request, db: Session = Depends(get_db), current_owner: models.Owner = Depends(security.get_current_owner)):
    _ = request.state.gettext.gettext
    
    bookings = crud.get_owner_bookings(db, owner_id=current_owner.id)
    
    services = json.loads(current_owner.services_json) if current_owner.services_json else []
    availability = json.loads(current_owner.availability_json) if current_owner.availability_json else {}

    context = {
        "request": request,
        "owner": current_owner,
        "bookings": bookings,
        "services": services,
        "availability": availability,
        "_": request.state.gettext.gettext
    }
    return request.state.templates.get_template("dashboard.html").render(context)

@app.post("/dashboard/profile", response_class=HTMLResponse, tags=["Owner Dashboard"])
async def update_owner_profile(request: Request, db: Session = Depends(get_db),
                               current_owner: models.Owner = Depends(security.get_current_owner),
                               name: str = Form(...), business_name: str = Form(...), phone: Optional[str] = Form(None)):
    _ = request.state.gettext.gettext
    try:
        owner_update = schemas.OwnerProfileUpdate(name=name, business_name=business_name, phone=phone)
        crud.update_owner_profile(db, current_owner, owner_update)
        response = RedirectResponse(url="/dashboard?message=profile_updated", status_code=status.HTTP_303_SEE_OTHER)
        return response
    except Exception as e:
        logger.error(f"Profile update error for owner {current_owner.id}: {e}")
        # Re-render dashboard with error message
        bookings = crud.get_owner_bookings(db, owner_id=current_owner.id)
        services = json.loads(current_owner.services_json) if current_owner.services_json else []
        availability = json.loads(current_owner.availability_json) if current_owner.availability_json else {}
        context = {
            "request": request,
            "owner": current_owner,
            "bookings": bookings,
            "services": services,
            "availability": availability,
            "error": _("Failed to update profile. Please try again."),
            "_": request.state.gettext.gettext
        }
        return request.state.templates.get_template("dashboard.html").render(context)


@app.post("/dashboard/services", response_class=HTMLResponse, tags=["Owner Dashboard"])
async def update_owner_services(request: Request, db: Session = Depends(get_db),
                                current_owner: models.Owner = Depends(security.get_current_owner),
                                services_data: str = Form(...)): # services_data will be a JSON string
    _ = request.state.gettext.gettext
    try:
        services_list = json.loads(services_data)
        # Validate each service in the list
        validated_services = [schemas.ServiceCreate(**s) for s in services_list]
        current_owner.services_json = json.dumps([s.dict() for s in validated_services])
        db.add(current_owner)
        db.commit()
        db.refresh(current_owner)
        response = RedirectResponse(url="/dashboard?message=services_updated", status_code=status.HTTP_303_SEE_OTHER)
        return response
    except json.JSONDecodeError:
        error_message = _("Invalid JSON format for services. Please correct it.")
    except Exception as e:
        logger.error(f"Service update error for owner {current_owner.id}: {e}")
        error_message = _("Failed to update services. Please try again.")
    
    # Re-render dashboard with error message if something went wrong
    bookings = crud.get_owner_bookings(db, owner_id=current_owner.id)
    services = json.loads(current_owner.services_json) if current_owner.services_json else []
    availability = json.loads(current_owner.availability_json) if current_owner.availability_json else {}
    context = {
        "request": request,
        "owner": current_owner,
        "bookings": bookings,
        "services": services,
        "availability": availability,
        "error": error_message if 'error_message' in locals() else _("An unexpected error occurred."),
        "_": request.state.gettext.gettext
    }
    return request.state.templates.get_template("dashboard.html").render(context)

@app.post("/dashboard/availability", response_class=HTMLResponse, tags=["Owner Dashboard"])
async def update_owner_availability(request: Request, db: Session = Depends(get_db),
                                    current_owner: models.Owner = Depends(security.get_current_owner),
                                    availability_data: str = Form(...)): # availability_data will be a JSON string
    _ = request.state.gettext.gettext
    try:
        availability_dict = json.loads(availability_data)
        # Basic validation for availability structure (can be expanded)
        for day, slots in availability_dict.items():
            if not isinstance(slots, list):
                raise ValueError(f"Slots for {day} must be a list.")
            for slot in slots:
                schemas.AvailabilitySlot(**slot) # Validate each slot
        
        current_owner.availability_json = json.dumps(availability_dict)
        db.add(current_owner)
        db.commit()
        db.refresh(current_owner)
        response = RedirectResponse(url="/dashboard?message=availability_updated", status_code=status.HTTP_303_SEE_OTHER)
        return response
    except json.JSONDecodeError:
        error_message = _("Invalid JSON format for availability. Please correct it.")
    except ValueError as ve:
        error_message = _(f"Validation error in availability: {ve}")
    except Exception as e:
        logger.error(f"Availability update error for owner {current_owner.id}: {e}")
        error_message = _("Failed to update availability. Please try again.")

    # Re-render dashboard with error message if something went wrong
    bookings = crud.get_owner_bookings(db, owner_id=current_owner.id)
    services = json.loads(current_owner.services_json) if current_owner.services_json else []
    availability = json.loads(current_owner.availability_json) if current_owner.availability_json else {}
    context = {
        "request": request,
        "owner": current_owner,
        "bookings": bookings,
        "services": services,
        "availability": availability,
        "error": error_message if 'error_message' in locals() else _("An unexpected error occurred."),
        "_": request.state.gettext.gettext
    }
    return request.state.templates.get_template("dashboard.html").render(context)

@app.get("/{owner_slug}", response_class=HTMLResponse, tags=["Public Booking Page"])
async def public_booking_page(request: Request, owner_slug: str, db: Session = Depends(get_db)):
    _ = request.state.gettext.gettext
    owner = crud.get_owner_by_slug(db, slug=owner_slug)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Owner not found"))

    services = json.loads(owner.services_json) if owner.services_json else []
    availability = json.loads(owner.availability_json) if owner.availability_json else {}

    context = {
        "request": request,
        "owner": owner,
        "services": services,
        "availability": availability,
        "_": request.state.gettext.gettext
    }
    return request.state.templates.get_template("booking_page.html").render(context)

@app.post("/{owner_slug}/book", response_class=HTMLResponse, tags=["Public Booking Page"])
async def submit_booking(request: Request, owner_slug: str, db: Session = Depends(get_db),
                         customer_name: str = Form(...), customer_email: EmailStr = Form(...),
                         customer_phone: Optional[str] = Form(None), service_name: str = Form(...),
                         booking_date: date = Form(...), booking_time: time = Form(...)):
    
    _ = request.state.gettext.gettext

    owner = crud.get_owner_by_slug(db, slug=owner_slug)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Owner not found"))

    try:
        booking_data = schemas.BookingCreate(
            customer_name=customer_name,
            customer_email=customer_email,
            customer_phone=customer_phone,
            service_name=service_name,
            booking_date=booking_date,
            booking_time=booking_time
        )
        booking = crud.create_booking(db=db, booking=booking_data, owner_id=owner.id)

        # Send email notifications
        owner_subject = _("New Booking Received!")
        owner_html_content = request.state.templates.get_template("email/owner_notification.html").render({
            "owner_name": owner.name,
            "customer_name": customer_name,
            "customer_email": customer_email,
            "customer_phone": customer_phone,
            "service_name": service_name,
            "booking_date": booking_date.strftime("%Y-%m-%d"),
            "booking_time": booking_time.strftime("%H:%M"),
            "_": request.state.gettext.gettext
        })
        notifications.send_email(owner.email, owner_subject, owner_html_content)

        customer_subject = _("Your Booking is Confirmed!")
        customer_html_content = request.state.templates.get_template("email/customer_confirmation.html").render({
            "customer_name": customer_name,
            "owner_business_name": owner.business_name,
            "service_name": service_name,
            "booking_date": booking_date.strftime("%Y-%m-%d"),
            "booking_time": booking_time.strftime("%H:%M"),
            "_": request.state.gettext.gettext
        })
        notifications.send_email(customer_email, customer_subject, customer_html_content)

        # Send WhatsApp notification to owner if phone is available
        if owner.phone:
            whatsapp_message = _("New booking for {service_name} on {booking_date} at {booking_time} by {customer_name}. Contact: {customer_phone} / {customer_email}.").format(
                service_name=service_name, booking_date=booking_date.strftime("%Y-%m-%d"), booking_time=booking_time.strftime("%H:%M"),
                customer_name=customer_name, customer_phone=customer_phone if customer_phone else _("N/A"), customer_email=customer_email
            )
            notifications.send_whatsapp_message(owner.phone, whatsapp_message)

        response = RedirectResponse(url=f"/{owner_slug}/confirmation", status_code=status.HTTP_303_SEE_OTHER)
        response.set_cookie(key="last_booking_customer_name", value=customer_name, httponly=True, max_age=300)
        response.set_cookie(key="last_booking_service_name", value=service_name, httponly=True, max_age=300)
        response.set_cookie(key="last_booking_date", value=booking_date.isoformat(), httponly=True, max_age=300)
        response.set_cookie(key="last_booking_time", value=booking_time.isoformat(timespec='minutes'), httponly=True, max_age=300)
        return response

    except Exception as e:
        logger.error(f"Booking submission error for owner {owner_slug}: {e}")
        # Re-render booking page with error message
        services = json.loads(owner.services_json) if owner.services_json else []
        availability = json.loads(owner.availability_json) if owner.availability_json else {}
        context = {
            "request": request,
            "owner": owner,
            "services": services,
            "availability": availability,
            "error": _("Failed to submit booking. Please check your details and try again."),
            "_": request.state.gettext.gettext
        }
        return request.state.templates.get_template("booking_page.html").render(context)

@app.get("/{owner_slug}/confirmation", response_class=HTMLResponse, tags=["Public Booking Page"])
async def booking_confirmation_page(request: Request, owner_slug: str, db: Session = Depends(get_db)):
    _ = request.state.gettext.gettext
    owner = crud.get_owner_by_slug(db, slug=owner_slug)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Owner not found"))

    customer_name = request.cookies.get("last_booking_customer_name")
    service_name = request.cookies.get("last_booking_service_name")
    booking_date_str = request.cookies.get("last_booking_date")
    booking_time_str = request.cookies.get("last_booking_time")

    context = {
        "request": request,
        "owner": owner,
        "customer_name": customer_name,
        "service_name": service_name,
        "booking_date": booking_date_str,
        "booking_time": booking_time_str,
        "_": request.state.gettext.gettext
    }
    response = request.state.templates.get_template("booking_confirmation.html").render(context)
    # Clear booking cookies after display
    response_obj = Response(content=response, media_type="text/html")
    response_obj.delete_cookie("last_booking_customer_name")
    response_obj.delete_cookie("last_booking_service_name")
    response_obj.delete_cookie("last_booking_date")
    response_obj.delete_cookie("last_booking_time")
    return response_obj

@app.get("/set-language/{lang}", tags=["Internationalization"])
async def set_language(request: Request, lang: str):
    response = RedirectResponse(url=request.headers.get("referer", "/"), status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(key="lang", value=lang, expires=3600 * 24 * 30) # 30 days
    return response
