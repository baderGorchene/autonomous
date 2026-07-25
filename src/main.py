from fastapi import FastAPI, Depends, HTTPException, status, Request, Response, Form
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import timedelta, date, datetime
from typing import List, Dict, Any, Optional
import json
import os
import gettext
from starlette.middleware.sessions import SessionMiddleware

from . import models, schemas, crud, security, notifications
from .database import SessionLocal, engine
from .config import settings
from .i18n_config import get_jinja_env # Import the configured Jinja2 environment

# Create database tables
models.Base.metadata.create_all(bind=engine)

app = FastAPI()

# Add SessionMiddleware for flash messages and locale
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Dependency to get current owner
async def get_current_owner(request: Request, db: Session = Depends(get_db)):
    token = request.session.get("access_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
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

# Dependency to get locale
def get_locale(request: Request):
    # Check query parameter first
    locale = request.query_params.get("lang")
    if locale in ['en', 'ar', 'fr']:
        request.session["locale"] = locale
        return locale
    
    # Check session
    locale = request.session.get("locale")
    if locale in ['en', 'ar', 'fr']:
        return locale
        
    # Check Accept-Language header (simplified)
    accept_language = request.headers.get("accept-language", "en").split(',')[0].lower()
    if 'ar' in accept_language:
        request.session["locale"] = 'ar'
        return 'ar'
    elif 'fr' in accept_language:
        request.session["locale"] = 'fr'
        return 'fr'
    
    # Default to English
    request.session["locale"] = 'en'
    return 'en'

# Templating setup with i18n
@app.middleware("http")
async def add_gettext_and_templates_to_request(request: Request, call_next):
    locale = get_locale(request)
    request.state.locale = locale
    request.state.gettext = gettext.translation('messages', localedir=os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'locales'), languages=[locale], fallback=True)
    request.state.templates = get_jinja_env(locale)
    response = await call_next(request)
    return response

# Helper function for flash messages
def flash(request: Request, message: str, category: str = "info"):
    if "_messages" not in request.session:
        request.session["_messages"] = []
    request.session["_messages"].append({"message": message, "category": category})

def get_flashed_messages(request: Request):
    messages = request.session.pop("_messages", [])
    return messages

# --- Authentication and Authorization ---
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    templates = request.state.templates
    return templates.get_template("login.html").render({"request": request, "messages": get_flashed_messages(request)})

@app.post("/token")
async def login_for_access_token(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    form_data: OAuth2PasswordRequestForm = Depends()
):
    owner = crud.authenticate_owner(db, form_data.username, form_data.password)
    if not owner:
        flash(request, request.state.gettext.gettext("Incorrect email or password"), "danger")
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": owner.email}, expires_delta=access_token_expires
    )
    request.session["access_token"] = access_token
    request.session["token_type"] = "bearer"
    flash(request, request.state.gettext.gettext("Logged in successfully!"), "success")
    return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/logout")
async def logout(request: Request):
    request.session.pop("access_token", None)
    request.session.pop("token_type", None)
    request.session.pop("locale", None) # Clear locale on logout
    flash(request, request.state.gettext.gettext("You have been logged out."), "info")
    return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

# --- Owner Signup ---
@app.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request):
    templates = request.state.templates
    return templates.get_template("signup.html").render({"request": request, "messages": get_flashed_messages(request)})

@app.post("/signup", response_class=HTMLResponse)
async def create_owner_signup(
    request: Request,
    db: Session = Depends(get_db),
    name: str = Form(...),
    business_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    slug: str = Form(...)
):
    templates = request.state.templates
    _ = request.state.gettext.gettext
    
    db_owner = crud.get_owner_by_email(db, email=email)
    if db_owner:
        flash(request, _("Email already registered"), "danger")
        return templates.get_template("signup.html").render({"request": request, "messages": get_flashed_messages(request), "form_data": {"name": name, "business_name": business_name, "email": email, "slug": slug}})
    
    db_owner = crud.get_owner_by_slug(db, slug=slug)
    if db_owner:
        flash(request, _("Business URL (slug) already taken"), "danger")
        return templates.get_template("signup.html").render({"request": request, "messages": get_flashed_messages(request), "form_data": {"name": name, "business_name": business_name, "email": email, "slug": slug}})

    try:
        owner_create = schemas.OwnerCreate(
            name=name,
            business_name=business_name,
            email=email,
            password=password,
            slug=slug
        )
        owner = crud.create_owner(db=db, owner=owner_create)
        
        # Log in the new owner immediately
        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = security.create_access_token(
            data={"sub": owner.email}, expires_delta=access_token_expires
        )
        request.session["access_token"] = access_token
        request.session["token_type"] = "bearer"

        flash(request, _("Account created successfully! Welcome to BookSlot."), "success")
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        flash(request, _(f"An error occurred during signup: {e}"), "danger")
        return templates.get_template("signup.html").render({"request": request, "messages": get_flashed_messages(request), "form_data": {"name": name, "business_name": business_name, "email": email, "slug": slug}})

# --- Owner Dashboard ---
@app.get("/dashboard", response_class=HTMLResponse)
async def read_dashboard(request: Request, db: Session = Depends(get_db), current_owner: models.Owner = Depends(get_current_owner)):
    templates = request.state.templates
    _ = request.state.gettext.gettext
    
    # Get upcoming bookings for the current owner
    upcoming_bookings = db.query(models.Booking).filter(
        models.Booking.owner_id == current_owner.id,
        models.Booking.booking_date >= date.today()
    ).order_by(models.Booking.booking_date, models.Booking.booking_time).all()

    # Parse services and availability
    services = json.loads(current_owner.services_json) if current_owner.services_json else []
    availability = json.loads(current_owner.availability_json) if current_owner.availability_json else {}

    return templates.get_template("dashboard.html").render({
        "request": request,
        "owner": current_owner,
        "upcoming_bookings": upcoming_bookings,
        "services": services,
        "availability": availability,
        "messages": get_flashed_messages(request),
        "locale": request.state.locale
    })

@app.get("/profile", response_class=HTMLResponse)
async def owner_profile_page(request: Request, current_owner: models.Owner = Depends(get_current_owner)):
    templates = request.state.templates
    _ = request.state.gettext.gettext
    
    services = json.loads(current_owner.services_json) if current_owner.services_json else []
    availability = json.loads(current_owner.availability_json) if current_owner.availability_json else []

    return templates.get_template("owner_profile.html").render({
        "request": request,
        "owner": current_owner,
        "services": services,
        "availability": availability,
        "messages": get_flashed_messages(request),
        "locale": request.state.locale
    })

@app.post("/profile", response_class=HTMLResponse)
async def update_owner_profile_post(
    request: Request,
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(get_current_owner),
    name: str = Form(...),
    business_name: str = Form(...),
    phone: Optional[str] = Form(None),
    services_json: str = Form(...), # JSON string from form
    availability_json: str = Form(...) # JSON string from form
):
    templates = request.state.templates
    _ = request.state.gettext.gettext

    try:
        # Validate services and availability JSON
        parsed_services = json.loads(services_json)
        parsed_availability = json.loads(availability_json)
        
        # Convert to Pydantic models for validation
        validated_services = [schemas.Service(**s) for s in parsed_services]
        validated_availability = [schemas.Availability(**a) for a in parsed_availability]

        owner_update_data = schemas.OwnerProfileUpdate(
            name=name,
            business_name=business_name,
            phone=phone,
            services=validated_services,
            availability=validated_availability
        )
        
        # Update owner details
        current_owner.name = owner_update_data.name
        current_owner.business_name = owner_update_data.business_name
        current_owner.phone = owner_update_data.phone
        current_owner.services_json = json.dumps([s.dict() for s in validated_services])
        current_owner.availability_json = json.dumps([a.dict() for a in validated_availability])
        
        db.add(current_owner)
        db.commit()
        db.refresh(current_owner)

        flash(request, _("Profile updated successfully!"), "success")
        return RedirectResponse(url="/profile", status_code=status.HTTP_303_SEE_OTHER)

    except json.JSONDecodeError:
        flash(request, _("Invalid JSON format for services or availability."), "danger")
    except Exception as e:
        flash(request, _(f"Error updating profile: {e}"), "danger")
    
    # If error, re-render with current data and messages
    services = json.loads(current_owner.services_json) if current_owner.services_json else []
    availability = json.loads(current_owner.availability_json) if current_owner.availability_json else []

    return templates.get_template("owner_profile.html").render({
        "request": request,
        "owner": current_owner,
        "services": services,
        "availability": availability,
        "messages": get_flashed_messages(request),
        "locale": request.state.locale
    })


# --- Public Booking Page ---
@app.get("/book/{owner_slug}", response_class=HTMLResponse)
async def public_booking_page(request: Request, owner_slug: str, db: Session = Depends(get_db)):
    templates = request.state.templates
    _ = request.state.gettext.gettext

    owner = crud.get_owner_by_slug(db, owner_slug)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Owner not found"))

    services = json.loads(owner.services_json) if owner.services_json else []
    availability = json.loads(owner.availability_json) if owner.availability_json else []

    # Prepare data for rendering
    context = {
        "request": request,
        "owner": owner,
        "services": services,
        "availability": availability,
        "messages": get_flashed_messages(request),
        "locale": request.state.locale
    }
    return templates.get_template("booking_page.html").render(context)

@app.post("/book/{owner_slug}", response_class=HTMLResponse)
async def submit_booking(
    request: Request,
    owner_slug: str,
    db: Session = Depends(get_db),
    customer_name: str = Form(...),
    customer_email: str = Form(...),
    customer_phone: Optional[str] = Form(None),
    service_name: str = Form(...),
    booking_date: str = Form(...), # YYYY-MM-DD
    booking_time: str = Form(...)  # HH:MM
):
    templates = request.state.templates
    _ = request.state.gettext.gettext
    
    owner = crud.get_owner_by_slug(db, owner_slug)
    if not owner:
        flash(request, _("Owner not found."), "danger")
        return RedirectResponse(url=f"/book/{owner_slug}", status_code=status.HTTP_303_SEE_OTHER)

    try:
        parsed_date = datetime.strptime(booking_date, "%Y-%m-%d").date()
        
        # Basic validation: ensure booking is not in the past
        if parsed_date < date.today():
            flash(request, _("Cannot book a date in the past."), "danger")
            return RedirectResponse(url=f"/book/{owner_slug}", status_code=status.HTTP_303_SEE_OTHER)

        # Further validation: check against owner's availability (simplified for now)
        # This would involve parsing availability_json and checking if the chosen date/time falls within it.
        # For MVP, we'll assume availability is handled client-side or is more flexible.

        booking_create = schemas.BookingCreate(
            customer_name=customer_name,
            customer_email=customer_email,
            customer_phone=customer_phone,
            service_name=service_name,
            booking_date=parsed_date,
            booking_time=booking_time
        )
        
        db_booking = crud.create_booking(db=db, booking=booking_create, owner_id=owner.id)

        # Send notifications
        owner_email_content = notifications.format_owner_notification(
            booking_data=booking_create.dict(),
            business_name=owner.business_name,
            owner_name=owner.name,
            locale=request.state.locale
        )
        notifications.send_email_notification(
            to_email=owner.email,
            subject=_(f"New Booking for {owner.business_name}"),
            html_content=owner_email_content
        )
        if owner.phone:
            owner_whatsapp_content = notifications.format_owner_whatsapp_notification(
                booking_data=booking_create.dict(),
                business_name=owner.business_name,
                owner_name=owner.name,
                locale=request.state.locale
            )
            notifications.send_whatsapp_notification(
                to_phone=owner.phone,
                message_body=owner_whatsapp_content
            )

        customer_email_content = notifications.format_booking_details(
            booking_data=booking_create.dict(),
            owner_name=owner.name,
            business_name=owner.business_name,
            locale=request.state.locale
        )
        notifications.send_email_notification(
            to_email=customer_email,
            subject=_(f"Your Booking Confirmation with {owner.business_name}"),
            html_content=customer_email_content
        )

        flash(request, _("Booking confirmed! A confirmation email has been sent."), "success")
        return RedirectResponse(url=f"/book/{owner_slug}/confirmation", status_code=status.HTTP_303_SEE_OTHER)

    except ValueError:
        flash(request, _("Invalid date or time format."), "danger")
    except Exception as e:
        flash(request, _(f"An error occurred during booking: {e}"), "danger")
    
    # If error, redirect back to booking page with form data (optional, for MVP just redirect)
    return RedirectResponse(url=f"/book/{owner_slug}", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/book/{owner_slug}/confirmation", response_class=HTMLResponse)
async def booking_confirmation_page(request: Request, owner_slug: str, db: Session = Depends(get_db)):
    templates = request.state.templates
    _ = request.state.gettext.gettext

    owner = crud.get_owner_by_slug(db, owner_slug)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Owner not found"))

    context = {
        "request": request,
        "owner": owner,
        "messages": get_flashed_messages(request),
        "locale": request.state.locale
    }
    return templates.get_template("booking_confirmation.html").render(context)

# --- Health Check ---
@app.get("/health")
async def health_check():
    return {"status": "ok"}
