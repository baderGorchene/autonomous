from fastapi import FastAPI, Depends, HTTPException, status, Request, Form, Response
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from . import crud, models, schemas, security, notifications
from .database import SessionLocal, engine, create_tables, get_db
from .dependencies import get_current_owner
from datetime import timedelta, date, datetime
from typing import List, Dict, Any, Optional
import json
import logging
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from src.config import settings
from src.i18n import _, set_locale, get_locale, get_catalog
from babel.dates import format_date, format_datetime, format_time
from babel.numbers import format_currency

# Initialize logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Add Session Middleware for CSRF protection and locale storage
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

# Directory for templates
templates = Jinja2Templates(directory="templates")

# Jinja2 i18n filter
@app.on_event("startup")
def setup_jinja_i18n():
    templates.env.add_extension('jinja2.ext.i18n')
    templates.env.install_gettext_callables(
        lambda x: _(x, locale_code=get_locale()),
        lambda s, p, n: _(s, p, n, locale_code=get_locale()),
        newstyle=True
    )

    def currency_filter(value: float, currency: str = "USD", locale: str = 'en'):
        try:
            return format_currency(value, currency, locale=locale)
        except Exception as e:
            logger.error(f"Error formatting currency {value} {currency} for locale {locale}: {e}")
            return f"{value} {currency}"

    templates.env.filters['currency'] = currency_filter

# Middleware for locale detection
class LocaleMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        lang = request.query_params.get("lang")
        if lang:
            set_locale(lang)
            request.session["locale"] = lang
        elif "locale" in request.session:
            set_locale(request.session["locale"])
        else:
            set_locale("en") # Default locale

        response = await call_next(request)
        return response

app.add_middleware(LocaleMiddleware)

@app.on_event("startup")
def on_startup():
    create_tables()
    logger.info("Database tables created/checked.")

@app.get("/health", response_class=JSONResponse)
def health_check():
    return {"status": "ok"}

@app.post("/token", response_model=schemas.Token)
async def login_for_access_token(response: Response, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    owner = crud.authenticate_owner(db, form_data.username, form_data.password)
    if not owner:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_("Incorrect email or password", locale_code=get_locale()),
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": owner.email}, expires_delta=access_token_expires
    )
    response.set_cookie(key="access_token", value=access_token, httponly=True, samesite="Lax", secure=True) # Secure=True in prod
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "gettext": _})

@app.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request):
    return templates.TemplateResponse("signup.html", {"request": request, "gettext": _})

@app.post("/signup", response_class=HTMLResponse)
async def register_owner(request: Request,
                         name: str = Form(...),
                         email: str = Form(...),
                         password: str = Form(...),
                         business_name: str = Form(...),
                         slug: str = Form(...),
                         phone: Optional[str] = Form(None),
                         db: Session = Depends(get_db)):
    db_owner = crud.get_owner_by_email(db, email=email)
    if db_owner:
        return templates.TemplateResponse("signup.html", {"request": request, "error": _("Email already registered", locale_code=get_locale()), "gettext": _})
    db_owner = crud.get_owner_by_slug(db, slug=slug)
    if db_owner:
        return templates.TemplateResponse("signup.html", {"request": request, "error": _("Business URL already taken", locale_code=get_locale()), "gettext": _})

    owner_create = schemas.OwnerCreate(name=name, email=email, password=password, business_name=business_name, slug=slug, phone=phone)
    crud.create_owner(db=db, owner=owner_create)
    return templates.TemplateResponse("login.html", {"request": request, "message": _("Registration successful! Please log in.", locale_code=get_locale()), "gettext": _})

@app.get("/logout")
async def logout(response: Response):
    response = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    response.delete_cookie(key="access_token")
    return response

@app.get("/dashboard", response_class=HTMLResponse)
async def owner_dashboard(request: Request, db: Session = Depends(get_db), current_owner: models.Owner = Depends(get_current_owner)):
    bookings = crud.get_owner_bookings(db, current_owner.id)
    services = json.loads(current_owner.services_json) if current_owner.services_json else []
    availability = json.loads(current_owner.availability_json) if current_owner.availability_json else {}

    # Filter upcoming bookings
    today = date.today()
    upcoming_bookings = [
        b for b in bookings
        if b.booking_date >= today
    ]
    upcoming_bookings.sort(key=lambda b: (b.booking_date, b.booking_time))

    # Prepare data for rendering
    owner_data = {
        "name": current_owner.name,
        "email": current_owner.email,
        "business_name": current_owner.business_name,
        "phone": current_owner.phone,
        "slug": current_owner.slug
    }

    # Format dates and times for display
    locale_code = get_locale()
    for booking in upcoming_bookings:
        booking.display_date = format_date(booking.booking_date, format='full', locale=locale_code)
        booking.display_time = format_time(datetime.strptime(booking.booking_time, "%H:%M").time(), format='short', locale=locale_code)

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "owner": owner_data,
        "bookings": upcoming_bookings,
        "services": services,
        "availability": availability,
        "gettext": _,
        "current_locale": locale_code
    })

@app.post("/dashboard/profile", response_class=HTMLResponse)
async def update_owner_profile_post(
    request: Request,
    name: str = Form(...),
    business_name: str = Form(...),
    phone: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(get_current_owner)
):
    try:
        owner_update = schemas.OwnerProfileUpdate(name=name, business_name=business_name, phone=phone)
        updated_owner = crud.update_owner_profile(db, current_owner, owner_update)
        success_message = _("Profile updated successfully!", locale_code=get_locale())
        
        # Redirect to dashboard to show updated data and success message
        response = RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
        request.session["message"] = success_message
        return response
    except Exception as e:
        logger.error(f"Error updating owner profile: {e}")
        error_message = _("Failed to update profile. Please try again.", locale_code=get_locale())
        
        # Render dashboard with error message
        bookings = crud.get_owner_bookings(db, current_owner.id)
        services = json.loads(current_owner.services_json) if current_owner.services_json else []
        availability = json.loads(current_owner.availability_json) if current_owner.availability_json else {}
        owner_data = {
            "name": current_owner.name,
            "email": current_owner.email,
            "business_name": current_owner.business_name,
            "phone": current_owner.phone,
            "slug": current_owner.slug
        }
        return templates.TemplateResponse("dashboard.html", {
            "request": request,
            "owner": owner_data,
            "bookings": bookings,
            "services": services,
            "availability": availability,
            "error": error_message,
            "gettext": _,
            "current_locale": get_locale()
        })

@app.post("/dashboard/services-availability", response_class=HTMLResponse)
async def update_services_availability(
    request: Request,
    services_json: str = Form(...),
    availability_json: str = Form(...),
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(get_current_owner)
):
    try:
        # Validate JSON inputs (optional but recommended)
        services_data = json.loads(services_json)
        availability_data = json.loads(availability_json)

        # Update owner's services and availability
        current_owner.services_json = json.dumps(services_data)
        current_owner.availability_json = json.dumps(availability_data)
        db.add(current_owner)
        db.commit()
        db.refresh(current_owner)
        
        success_message = _("Services and availability updated successfully!", locale_code=get_locale())
        response = RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
        request.session["message"] = success_message
        return response
    except json.JSONDecodeError:
        error_message = _("Invalid JSON format for services or availability.", locale_code=get_locale())
        response = RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
        request.session["error"] = error_message
        return response
    except Exception as e:
        logger.error(f"Error updating services/availability: {e}")
        error_message = _("Failed to update services and availability. Please try again.", locale_code=get_locale())
        response = RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
        request.session["error"] = error_message
        return response

@app.get("/{owner_slug}", response_class=HTMLResponse)
async def booking_page(owner_slug: str, request: Request, db: Session = Depends(get_db)):
    owner = crud.get_owner_by_slug(db, owner_slug)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Owner not found", locale_code=get_locale()))

    services = json.loads(owner.services_json) if owner.services_json else []
    availability = json.loads(owner.availability_json) if owner.availability_json else {}

    # Generate CSRF token
    csrf_token = security.create_access_token(data={"sub": "csrf"}, expires_delta=timedelta(minutes=10))
    request.session["csrf_token"] = csrf_token

    return templates.TemplateResponse("booking_page.html", {
        "request": request,
        "owner": owner,
        "services": services,
        "availability": availability,
        "csrf_token": csrf_token,
        "gettext": _,
        "current_locale": get_locale(),
        "server_name": settings.SERVER_NAME
    })

@app.post("/{owner_slug}/book", response_class=HTMLResponse)
async def submit_booking(
    owner_slug: str,
    request: Request,
    customer_name: str = Form(...),
    customer_email: EmailStr = Form(...),
    customer_phone: Optional[str] = Form(None),
    service_name: str = Form(...),
    booking_date: str = Form(...),
    booking_time: str = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db)
):
    # CSRF protection
    if "csrf_token" not in request.session or request.session["csrf_token"] != csrf_token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_("Invalid CSRF token", locale_code=get_locale()))
    
    owner = crud.get_owner_by_slug(db, owner_slug)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Owner not found", locale_code=get_locale()))

    try:
        parsed_booking_date = datetime.strptime(booking_date, "%Y-%m-%d").date()
        # Basic validation: check if the date is in the future
        if parsed_booking_date < date.today():
             return templates.TemplateResponse("booking_page.html", {
                "request": request, "owner": owner, "services": json.loads(owner.services_json),
                "availability": json.loads(owner.availability_json), "error": _("Cannot book in the past.", locale_code=get_locale()),
                "csrf_token": csrf_token, "gettext": _, "current_locale": get_locale(), "server_name": settings.SERVER_NAME
            })

        booking_data = schemas.BookingCreate(
            customer_name=customer_name,
            customer_email=customer_email,
            customer_phone=customer_phone,
            service_name=service_name,
            booking_date=parsed_booking_date,
            booking_time=booking_time
        )
        
        db_booking = crud.create_booking(db=db, booking=booking_data, owner_id=owner.id)

        # Send notifications
        booking_details_for_notification = booking_data.model_dump()
        notifications.send_booking_confirmation_email(booking_details_for_notification, owner.business_name, owner.slug, locale=get_locale())
        notifications.send_booking_notification_to_owner(booking_details_for_notification, owner.email, owner.phone, owner.business_name, locale=get_locale())

        return RedirectResponse(url=f"/{owner_slug}/booked?booking_id={db_booking.id}", status_code=status.HTTP_303_SEE_OTHER)

    except ValueError as e:
        logger.error(f"Booking submission error (ValueError): {e}")
        # Re-render booking page with error message
        return templates.TemplateResponse("booking_page.html", {
            "request": request, "owner": owner, "services": json.loads(owner.services_json),
            "availability": json.loads(owner.availability_json), "error": _("Invalid date or time format.", locale_code=get_locale()),
            "csrf_token": csrf_token, "gettext": _, "current_locale": get_locale(), "server_name": settings.SERVER_NAME
        })
    except Exception as e:
        logger.error(f"Booking submission error: {e}")
        # Re-render booking page with a generic error message
        return templates.TemplateResponse("booking_page.html", {
            "request": request, "owner": owner, "services": json.loads(owner.services_json),
            "availability": json.loads(owner.availability_json), "error": _("Failed to process your booking. Please try again.", locale_code=get_locale()),
            "csrf_token": csrf_token, "gettext": _, "current_locale": get_locale(), "server_name": settings.SERVER_NAME
        })

@app.get("/{owner_slug}/booked", response_class=HTMLResponse)
async def booking_confirmation_page(owner_slug: str, request: Request, booking_id: int, db: Session = Depends(get_db)):
    owner = crud.get_owner_by_slug(db, owner_slug)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Owner not found", locale_code=get_locale()))
    
    booking = db.query(models.Booking).filter(models.Booking.id == booking_id, models.Booking.owner_id == owner.id).first()
    if not booking:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Booking not found", locale_code=get_locale()))

    locale_code = get_locale()
    booking.display_date = format_date(booking.booking_date, format='full', locale=locale_code)
    booking.display_time = format_time(datetime.strptime(booking.booking_time, "%H:%M").time(), format='short', locale=locale_code)

    return templates.TemplateResponse("booking_confirmation.html", {
        "request": request,
        "owner": owner,
        "booking": booking,
        "gettext": _,
        "current_locale": locale_code
    })