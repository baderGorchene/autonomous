from fastapi import FastAPI, Depends, Request, Form, HTTPException, status, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from . import models, schemas, crud, security, notifications
from .database import engine, get_db, create_tables
from .dependencies import get_current_owner
from .config import settings
from .i18n import _, set_locale, get_locale
from .utils import format_currency_filter # For Jinja2 filters
import datetime
import json
import os
import gettext
from typing import List, Optional, Dict, Any

# Ensure tables are created on startup
create_tables()

app = FastAPI()

# Setup static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Setup templates
templates = Jinja2Templates(directory="templates")

# Add i18n and other custom filters to Jinja2 environment
def init_jinja2_env():
    env = templates.env
    env.globals['gettext'] = _
    env.globals['_'] = _ # Alias for convenience
    env.globals['current_locale'] = get_locale
    env.filters['currency'] = format_currency_filter
    return env

templates.env = init_jinja2_env()

# Middleware for language detection
@app.middleware("http")
async def add_language_middleware(request: Request, call_next):
    lang_code = request.cookies.get("lang", "en")
    set_locale(lang_code)
    response = await call_next(request)
    return response

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request, db: Session = Depends(get_db)):
    # Check if an owner is logged in
    try:
        token = request.cookies.get("access_token")
        if token:
            # Attempt to decode token to see if it's valid
            payload = security.decode_access_token(token)
            if payload and payload.get("sub"):
                return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    except Exception:
        pass # Token might be invalid or expired

    return templates.TemplateResponse("login.html", {"request": request, "title": _("Welcome")})

@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request, "title": _("Register")})

@app.post("/register", response_class=HTMLResponse)
async def register_owner(
    request: Request,
    db: Session = Depends(get_db),
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    business_name: str = Form(...),
    slug: str = Form(...),
    phone: Optional[str] = Form(None)
):
    db_owner = crud.get_owner_by_email(db, email=email)
    if db_owner:
        return templates.TemplateResponse("register.html", {"request": request, "error": _("Email already registered"), "title": _("Register")})
    db_owner = crud.get_owner_by_slug(db, slug=slug)
    if db_owner:
        return templates.TemplateResponse("register.html", {"request": request, "error": _("Business URL already taken"), "title": _("Register")})

    try:
        owner = schemas.OwnerCreate(name=name, email=email, password=password, business_name=business_name, slug=slug, phone=phone)
        crud.create_owner(db=db, owner=owner)
        return templates.TemplateResponse("login.html", {"request": request, "message": _("Registration successful! Please log in."), "title": _("Login")})
    except Exception as e:
        return templates.TemplateResponse("register.html", {"request": request, "error": _(f"Registration failed: {e}"), "title": _("Register")})


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "title": _("Login")})

@app.post("/token", response_class=HTMLResponse)
async def login_for_access_token(
    request: Request,
    db: Session = Depends(get_db),
    username: str = Form(...), # Renamed from email to match OAuth2PasswordRequestForm
    password: str = Form(...)
):
    owner = crud.authenticate_owner(db, email=username, password=password)
    if not owner:
        return templates.TemplateResponse("login.html", {"request": request, "error": _("Incorrect email or password"), "title": _("Login")})
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": owner.email}, expires_delta=access_token_expires
    )
    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    response.set_cookie(key="access_token", value=access_token, httponly=True, samesite="lax")
    return response

@app.get("/logout")
async def logout(response: Response):
    response = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    response.delete_cookie(key="access_token")
    return response

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, current_owner: models.Owner = Depends(get_current_owner), db: Session = Depends(get_db)):
    bookings = crud.get_owner_bookings(db, owner_id=current_owner.id)
    # Filter for upcoming bookings
    today = datetime.date.today()
    upcoming_bookings = [
        b for b in bookings
        if b.booking_date >= today
    ]
    # Sort upcoming bookings
    upcoming_bookings.sort(key=lambda b: (b.booking_date, b.booking_time))

    # Parse services and availability
    services = json.loads(current_owner.services_json) if current_owner.services_json else []
    availability = json.loads(current_owner.availability_json) if current_owner.availability_json else {}

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "owner": current_owner,
            "upcoming_bookings": upcoming_bookings,
            "services": services,
            "availability": availability,
            "title": _("Dashboard")
        }
    )

@app.post("/dashboard/profile", response_class=HTMLResponse)
async def update_profile(
    request: Request,
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(get_current_owner),
    name: str = Form(...),
    business_name: str = Form(...),
    phone: Optional[str] = Form(None),
    services_json: str = Form("[]"),
    availability_json: str = Form("{}")
):
    try:
        owner_update = schemas.OwnerProfileUpdate(name=name, business_name=business_name, phone=phone)
        updated_owner = crud.update_owner_profile(db, current_owner, owner_update)

        # Update services and availability directly on the model
        updated_owner.services_json = services_json
        updated_owner.availability_json = availability_json
        db.add(updated_owner)
        db.commit()
        db.refresh(updated_owner)

        bookings = crud.get_owner_bookings(db, owner_id=updated_owner.id)
        today = datetime.date.today()
        upcoming_bookings = [
            b for b in bookings
            if b.booking_date >= today
        ]
        upcoming_bookings.sort(key=lambda b: (b.booking_date, b.booking_time))

        services = json.loads(updated_owner.services_json) if updated_owner.services_json else []
        availability = json.loads(updated_owner.availability_json) if updated_owner.availability_json else {}

        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "owner": updated_owner,
                "upcoming_bookings": upcoming_bookings,
                "services": services,
                "availability": availability,
                "message": _("Profile updated successfully!"),
                "title": _("Dashboard")
            }
        )
    except Exception as e:
        bookings = crud.get_owner_bookings(db, owner_id=current_owner.id)
        today = datetime.date.today()
        upcoming_bookings = [
            b for b in bookings
            if b.booking_date >= today
        ]
        upcoming_bookings.sort(key=lambda b: (b.booking_date, b.booking_time))

        services = json.loads(current_owner.services_json) if current_owner.services_json else []
        availability = json.loads(current_owner.availability_json) if current_owner.availability_json else {}

        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "owner": current_owner,
                "upcoming_bookings": upcoming_bookings,
                "services": services,
                "availability": availability,
                "error": _(f"Error updating profile: {e}"),
                "title": _("Dashboard")
            }
        )

@app.get("/{owner_slug}", response_class=HTMLResponse)
async def booking_page(request: Request, owner_slug: str, db: Session = Depends(get_db)):
    owner = crud.get_owner_by_slug(db, slug=owner_slug)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Booking page not found"))

    services_data = json.loads(owner.services_json) if owner.services_json else []
    availability_data = json.loads(owner.availability_json) if owner.availability_json else {}

    # Convert services and availability to Pydantic models for validation/structure
    services = [schemas.Service(**s) for s in services_data]
    availability = {day: [schemas.Availability(**a) for a in avail_list] for day, avail_list in availability_data.items()}

    booking_page_data = schemas.BookingPageData(
        owner_name=owner.name,
        business_name=owner.business_name,
        slug=owner.slug,
        services=services,
        availability=availability,
        current_lang=get_locale()
    )
    return templates.TemplateResponse("booking_page.html", {"request": request, "data": booking_page_data, "title": booking_page_data.business_name})

@app.post("/{owner_slug}/book", response_class=HTMLResponse)
async def submit_booking(
    request: Request,
    owner_slug: str,
    db: Session = Depends(get_db),
    customer_name: str = Form(...),
    customer_email: EmailStr = Form(...),
    customer_phone: Optional[str] = Form(None),
    service_name: str = Form(...),
    booking_date: str = Form(...), # YYYY-MM-DD
    booking_time: str = Form(...) # HH:MM AM/PM
):
    owner = crud.get_owner_by_slug(db, slug=owner_slug)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Booking page not found"))

    try:
        parsed_date = datetime.datetime.strptime(booking_date, "%Y-%m-%d").date()
        booking_data = schemas.BookingCreate(
            customer_name=customer_name,
            customer_email=customer_email,
            customer_phone=customer_phone,
            service_name=service_name,
            booking_date=parsed_date,
            booking_time=booking_time
        )
        crud.create_booking(db=db, booking=booking_data, owner_id=owner.id)

        # Send notifications
        formatted_notifications = notifications.format_booking_details(
            booking_data.model_dump(), owner.name, owner.business_name, get_locale()
        )

        # Notify owner via email
        notifications.send_email_notification(
            to_email=owner.email,
            subject=formatted_notifications["owner_email_subject"],
            html_content=formatted_notifications["owner_email_html"]
        )
        # Notify owner via WhatsApp
        if owner.phone:
            notifications.send_whatsapp_notification(
                to_phone=owner.phone,
                message_body=formatted_notifications["owner_whatsapp_msg"]
            )
        # Notify customer via email
        notifications.send_email_notification(
            to_email=customer_email,
            subject=formatted_notifications["customer_email_subject"],
            html_content=formatted_notifications["customer_email_html"]
        )
        # TODO: Potentially notify customer via WhatsApp if desired and customer_phone is provided

        return templates.TemplateResponse(
            "booking_confirmation.html",
            {"request": request, "message": _("Your booking has been successfully confirmed!"), "title": _("Booking Confirmed")}
        )
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_("Invalid date or time format."))
    except Exception as e:
        # Re-render booking page with error message
        services_data = json.loads(owner.services_json) if owner.services_json else []
        availability_data = json.loads(owner.availability_json) if owner.availability_json else {}
        services = [schemas.Service(**s) for s in services_data]
        availability = {day: [schemas.Availability(**a) for a in avail_list] for day, avail_list in availability_data.items()}
        booking_page_data = schemas.BookingPageData(
            owner_name=owner.name,
            business_name=owner.business_name,
            slug=owner.slug,
            services=services,
            availability=availability,
            current_lang=get_locale()
        )
        return templates.TemplateResponse(
            "booking_page.html",
            {
                "request": request,
                "data": booking_page_data,
                "error": _(f"Failed to submit booking: {e}"),
                "title": booking_page_data.business_name
            },
            status_code=status.HTTP_400_BAD_REQUEST
        )

@app.post("/set-language")
async def set_language(lang: str = Form(...), response: Response):
    response = RedirectResponse(url=f"/", status_code=status.HTTP_302_FOUND)
    response.set_cookie(key="lang", value=lang, samesite="lax")
    return response

# Catch-all route for language toggle on current page
@app.post("/set-language-redirect")
async def set_language_redirect(request: Request, lang: str = Form(...)):
    referer = request.headers.get("referer")
    response = RedirectResponse(url=referer or "/", status_code=status.HTTP_302_FOUND)
    response.set_cookie(key="lang", value=lang, samesite="lax")
    return response
