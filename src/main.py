from fastapi import FastAPI, Depends, HTTPException, status, Request, Response, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import pytz
import os
import gettext
import logging
from typing import Optional, List, Dict, Any
from urllib.parse import urlencode

from . import crud, models, schemas, security
from .database import SessionLocal, engine
from .config import settings
from .i18n_config import get_jinja_env
from .notifications import send_email_notification, send_whatsapp_notification

models.Base.metadata.create_all(bind=engine)

app = FastAPI()

logger = logging.getLogger(__name__)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

async def get_current_owner(db: Session = Depends(get_db), token: str = Depends(security.oauth2_scheme)):
    token_data = security.decode_access_token(token)
    owner = crud.get_owner_by_email(db, email=token_data.email)
    if owner is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Owner not found")
    return owner

def get_locale_from_request(request: Request) -> str:
    lang = request.query_params.get("lang")
    if lang in ["en", "ar", "fr"]:
        return lang
    lang = request.cookies.get("lang")
    if lang in ["en", "ar", "fr"]:
        return lang
    return "en"

def get_translator(locale: str):
    current_dir = os.path.dirname(__file__)
    project_root = os.path.abspath(os.path.join(current_dir, os.pardir))
    localedir = os.path.join(project_root, 'locales')
    try:
        t = gettext.translation('messages', localedir, languages=[locale], fallback=True)
    except FileNotFoundError:
        logger.warning(f"Translation file not found for locale: {locale} in {localedir}. Using fallback.")
        t = gettext.NullTranslations() # Fallback to no translation
    return t.gettext

@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "ok"}

@app.post("/token", response_model=schemas.Token, tags=["Auth"])
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
    response.set_cookie(key="access_token", value=access_token, httponly=True, expires=access_token_expires.total_seconds())
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/signup", response_class=HTMLResponse, tags=["Auth"])
async def signup_form(request: Request):
    locale = get_locale_from_request(request)
    env = get_jinja_env(locale=locale)
    template = env.get_template("signup.html")
    return template.render(request=request, current_locale=locale)

@app.post("/signup", response_class=HTMLResponse, tags=["Auth"])
async def signup_owner(request: Request, name: str = Form(...), email: EmailStr = Form(...),
                       password: str = Form(...), business_name: str = Form(...),
                       slug: str = Form(...), db: Session = Depends(get_db)):
    locale = get_locale_from_request(request)
    env = get_jinja_env(locale=locale)
    _ = get_translator(locale)
    
    db_owner = crud.get_owner_by_email(db, email=email)
    if db_owner:
        template = env.get_template("signup.html")
        return template.render(request=request, error=_("Email already registered"), name=name, email=email, business_name=business_name, slug=slug, current_locale=locale)
    
    db_owner = crud.get_owner_by_slug(db, slug=slug)
    if db_owner:
        template = env.get_template("signup.html")
        return template.render(request=request, error=_("Business URL slug already taken"), name=name, email=email, business_name=business_name, slug=slug, current_locale=locale)

    owner = schemas.OwnerCreate(name=name, email=email, password=password, business_name=business_name, slug=slug)
    crud.create_owner(db=db, owner=owner)
    
    return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)

@app.get("/dashboard", response_class=HTMLResponse, tags=["Owner"])
async def owner_dashboard(request: Request, db: Session = Depends(get_db), current_owner: models.Owner = Depends(get_current_owner)):
    locale = get_locale_from_request(request)
    env = get_jinja_env(locale=locale)
    template = env.get_template("dashboard.html")
    
    upcoming_bookings = [b for b in current_owner.bookings if b.booking_time > datetime.now(pytz.utc)]
    upcoming_bookings.sort(key=lambda b: b.booking_time)
    
    return template.render(
        request=request,
        owner=current_owner,
        upcoming_bookings=upcoming_bookings,
        current_locale=locale
    )

@app.post("/dashboard/profile", response_class=HTMLResponse, tags=["Owner"])
async def update_owner_profile(request: Request,
                               name: str = Form(...),
                               business_name: str = Form(...),
                               phone: Optional[str] = Form(None),
                               db: Session = Depends(get_db),
                               current_owner: models.Owner = Depends(get_current_owner)):
    locale = get_locale_from_request(request)
    env = get_jinja_env(locale=locale)
    _ = get_translator(locale)
    
    try:
        owner_update = schemas.OwnerProfileUpdate(name=name, business_name=business_name, phone=phone)
        updated_owner = crud.update_owner_profile(db, current_owner, owner_update)
        
        template = env.get_template("dashboard.html")
        upcoming_bookings = [b for b in updated_owner.bookings if b.booking_time > datetime.now(pytz.utc)]
        upcoming_bookings.sort(key=lambda b: b.booking_time)
        return template.render(
            request=request,
            owner=updated_owner,
            upcoming_bookings=upcoming_bookings,
            current_locale=locale,
            success_message=_("Profile updated successfully!")
        )
    except Exception as e:
        logger.error(f"Error updating owner profile: {e}")
        template = env.get_template("dashboard.html")
        upcoming_bookings = [b for b in current_owner.bookings if b.booking_time > datetime.now(pytz.utc)]
        upcoming_bookings.sort(key=lambda b: b.booking_time)
        return template.render(
            request=request,
            owner=current_owner,
            upcoming_bookings=upcoming_bookings,
            current_locale=locale,
            error_message=_("Failed to update profile. Please try again.")
        )

@app.get("/bookslot.app/{owner_slug}", response_class=HTMLResponse, tags=["Booking"])
async def public_booking_page(request: Request, owner_slug: str, db: Session = Depends(get_db)):
    locale = get_locale_from_request(request)
    env = get_jinja_env(locale=locale)
    template = env.get_template("booking_page.html")
    _ = get_translator(locale)
    
    owner = crud.get_owner_by_slug(db, slug=owner_slug)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Owner not found"))

    services = owner.services_json if owner.services_json else []
    
    mock_available_slots = [
        {"time": "09:00", "display": _("09:00 AM")},
        {"time": "10:00", "display": _("10:00 AM")},
        {"time": "11:00", "display": _("11:00 AM")},
        {"time": "14:00", "display": _("02:00 PM")},
        {"time": "15:00", "display": _("03:00 PM")},
    ]

    return template.render(
        request=request,
        owner=owner,
        services=services,
        available_slots=mock_available_slots,
        current_locale=locale
    )

@app.post("/bookslot.app/{owner_slug}/book", response_class=HTMLResponse, tags=["Booking"])
async def submit_booking(request: Request, owner_slug: str,
                         customer_name: str = Form(...),
                         customer_email: EmailStr = Form(...),
                         customer_phone: Optional[str] = Form(None),
                         service_name: str = Form(...),
                         booking_date: str = Form(...),
                         booking_time: str = Form(...),
                         db: Session = Depends(get_db)):
    locale = get_locale_from_request(request)
    env = get_jinja_env(locale=locale)
    _ = get_translator(locale)
    
    owner = crud.get_owner_by_slug(db, slug=owner_slug)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Owner not found"))
    
    try:
        booking_datetime_str = f"{booking_date} {booking_time}"
        booking_dt = datetime.strptime(booking_datetime_str, "%Y-%m-%d %H:%M").replace(tzinfo=pytz.utc)
        
        if booking_dt <= datetime.now(pytz.utc):
            raise ValueError(_("Booking must be in the future."))

        booking_data = schemas.BookingCreate(
            customer_name=customer_name,
            customer_email=customer_email,
            customer_phone=customer_phone,
            service_name=service_name,
            booking_time=booking_dt
        )
        db_booking = crud.create_booking(db=db, booking=booking_data, owner_id=owner.id)
        
        owner_subject = _("New Booking Received!")
        owner_body = _(f"Dear {owner.name},\n\nYou have a new booking from {customer_name} for {service_name} at {booking_dt.strftime('%Y-%m-%d %H:%M %Z')}.\nCustomer Email: {customer_email}\nCustomer Phone: {customer_phone or _('N/A')}")
        send_email_notification(owner.email, owner_subject, owner_body)
        if owner.phone:
            send_whatsapp_notification(owner.phone, owner_body)

        customer_subject = _("Your Booking Confirmation")
        customer_body = _(f"Dear {customer_name},\n\nYour booking for {service_name} with {owner.business_name} at {booking_dt.strftime('%Y-%m-%d %H:%M %Z')} has been confirmed.\n\nThank you!")
        send_email_notification(customer_email, customer_subject, customer_body)
        if customer_phone:
            send_whatsapp_notification(customer_phone, customer_body)

        return RedirectResponse(url=f"/bookslot.app/{owner_slug}/confirmation?booking_id={db_booking.id}", status_code=status.HTTP_302_FOUND)
    
    except ValueError as ve:
        template = env.get_template("booking_page.html")
        services = owner.services_json if owner.services_json else []
        mock_available_slots = [
            {"time": "09:00", "display": _("09:00 AM")}, {"time": "10:00", "display": _("10:00 AM")},
            {"time": "11:00", "display": _("11:00 AM")}, {"time": "14:00", "display": _("02:00 PM")},
            {"time": "15:00", "display": _("03:00 PM")},
        ]
        return template.render(
            request=request, owner=owner, services=services,
            available_slots=mock_available_slots, current_locale=locale,
            error_message=str(ve),
            customer_name=customer_name, customer_email=customer_email,
            customer_phone=customer_phone, service_name=service_name,
            booking_date=booking_date, booking_time=booking_time
        )
    except Exception as e:
        logger.error(f"Error submitting booking: {e}")
        template = env.get_template("booking_page.html")
        services = owner.services_json if owner.services_json else []
        mock_available_slots = [
            {"time": "09:00", "display": _("09:00 AM")}, {"time": "10:00", "display": _("10:00 AM")},
            {"time": "11:00", "display": _("11:00 AM")}, {"time": "14:00", "display": _("02:00 PM")},
            {"time": "15:00", "display": _("03:00 PM")},
        ]
        return template.render(
            request=request, owner=owner, services=services,
            available_slots=mock_available_slots, current_locale=locale,
            error_message=_("Failed to submit booking. Please try again."),
            customer_name=customer_name, customer_email=customer_email,
            customer_phone=customer_phone, service_name=service_name,
            booking_date=booking_date, booking_time=booking_time
        )

@app.get("/bookslot.app/{owner_slug}/confirmation", response_class=HTMLResponse, tags=["Booking"])
async def booking_confirmation_page(request: Request, owner_slug: str, booking_id: int, db: Session = Depends(get_db)):
    locale = get_locale_from_request(request)
    env = get_jinja_env(locale=locale)
    template = env.get_template("booking_confirmation.html")
    
    return template.render(request=request, owner_slug=owner_slug, booking_id=booking_id, current_locale=locale)

@app.get("/toggle-lang", tags=["i18n"])
async def toggle_language(request: Request, response: Response, lang: str):
    if lang not in ["en", "ar", "fr"]:
        lang = "en"
    
    response = RedirectResponse(url=request.headers.get("referer", "/"), status_code=status.HTTP_302_FOUND)
    response.set_cookie(key="lang", value=lang, expires=2592000)
    return response

@app.get("/login", response_class=HTMLResponse, tags=["Auth"])
async def login_form(request: Request):
    locale = get_locale_from_request(request)
    env = get_jinja_env(locale=locale)
    template = env.get_template("login.html")
    return template.render(request=request, current_locale=locale)

@app.get("/logout", tags=["Auth"])
async def logout(response: Response):
    response = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    response.delete_cookie(key="access_token")
    return response
