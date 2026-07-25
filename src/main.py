from fastapi import FastAPI, Depends, HTTPException, status, Request, Form, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from . import crud, models, schemas, security, notifications
from .database import engine, SessionLocal
from .i18n_config import get_jinja_env
from .config import settings
import datetime
import json
from typing import List, Optional
import gettext
import os

# Create DB tables
models.Base.metadata.create_all(bind=engine)

app = FastAPI()

# Mount static files
current_file_dir = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(current_file_dir, os.pardir))
app.mount("/static", StaticFiles(directory=os.path.join(PROJECT_ROOT, "static")), name="static")

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.middleware("http")
async def add_language_cookie(request: Request, call_next):
    # Check for lang query parameter first, then cookie
    lang = request.query_params.get("lang")
    if not lang:
        lang = request.cookies.get("lang", "en") # Default to English
    
    response = await call_next(request)
    if lang != request.cookies.get("lang") and lang: # Only set if changed and not None
        response.set_cookie(key="lang", value=lang, httponly=True)
    return response

def get_locale(request: Request):
    return request.cookies.get("lang", "en")

def get_translator(request: Request):
    locale = get_locale(request)
    env = get_jinja_env(locale)
    return env.gettext

# Routes for authentication and owner management
@app.get("/health", response_class=HTMLResponse)
async def health_check():
    return "<h1>BookSlot is healthy!</h1>"

@app.get("/signup", response_class=HTMLResponse)
async def signup_form(request: Request):
    _ = get_translator(request)
    env = get_jinja_env(get_locale(request))
    template = env.get_template("signup.html")
    return template.render(request=request, _=_, current_lang=get_locale(request))

@app.post("/signup", response_class=RedirectResponse)
async def owner_signup(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    business_name: str = Form(...),
    slug: str = Form(...),
    db: Session = Depends(get_db)
):
    _ = get_translator(request)
    owner = crud.get_owner_by_email(db, email=email)
    if owner:
        return RedirectResponse(url="/signup?error=email_exists", status_code=status.HTTP_303_SEE_OTHER)
    
    owner = crud.get_owner_by_slug(db, slug=slug)
    if owner:
        return RedirectResponse(url="/signup?error=slug_exists", status_code=status.HTTP_303_SEE_OTHER)

    owner_in = schemas.OwnerCreate(name=name, email=email, password=password, business_name=business_name, slug=slug)
    crud.create_owner(db=db, owner=owner_in)
    return RedirectResponse(url="/login?message=signup_success", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/login", response_class=HTMLResponse)
async def login_form(request: Request):
    _ = get_translator(request)
    env = get_jinja_env(get_locale(request))
    template = env.get_template("login.html")
    return template.render(request=request, _=_, current_lang=get_locale(request))

@app.post("/token", response_model=schemas.Token)
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)
):
    owner = security.authenticate_owner(db, form_data.username, form_data.password)
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

# Route to handle login via form and set cookie
@app.post("/login", response_class=RedirectResponse)
async def owner_login_form(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    _ = get_translator(request)
    owner = security.authenticate_owner(db, email, password)
    if not owner:
        return RedirectResponse(url="/login?error=invalid_credentials", status_code=status.HTTP_303_SEE_OTHER)
    
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": owner.email}, expires_delta=access_token_expires
    )
    
    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(key="access_token", value=access_token, httponly=True)
    return response

@app.get("/logout", response_class=RedirectResponse)
async def logout(response: Response):
    response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(key="access_token")
    return response

@app.get("/dashboard", response_class=HTMLResponse)
async def owner_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(security.get_current_owner)
):
    _ = get_translator(request)
    env = get_jinja_env(get_locale(request))
    template = env.get_template("dashboard.html")

    # Fetch upcoming bookings for the current owner
    upcoming_bookings = db.query(models.Booking).filter(
        models.Booking.owner_id == current_owner.id,
        models.Booking.booking_time >= datetime.datetime.now()
    ).order_by(models.Booking.booking_time).all()
    
    owner_services = json.loads(current_owner.services_json) if current_owner.services_json else []
    owner_availability = json.loads(current_owner.availability_json) if current_owner.availability_json else []

    return template.render(
        request=request,
        owner=current_owner,
        bookings=upcoming_bookings,
        services=owner_services,
        availability=owner_availability,
        _=_, # Pass gettext function to template
        current_lang=get_locale(request)
    )

@app.post("/dashboard/profile", response_class=RedirectResponse)
async def update_owner_profile(
    request: Request,
    name: str = Form(...),
    business_name: str = Form(...),
    phone: Optional[str] = Form(None),
    services_json_str: Optional[str] = Form(None, alias="services"), # Expect JSON string from form
    availability_json_str: Optional[str] = Form(None, alias="availability"), # Expect JSON string from form
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(security.get_current_owner)
):
    _ = get_translator(request)
    
    try:
        services_data = json.loads(services_json_str) if services_json_str else []
        availability_data = json.loads(availability_json_str) if availability_json_str else []

        # Validate against schemas
        validated_services = [schemas.Service(**s) for s in services_data]
        validated_availability = [schemas.AvailabilitySlot(**a) for a in availability_data]

        owner_update = schemas.OwnerProfileUpdate(
            name=name,
            business_name=business_name,
            phone=phone,
            services=validated_services,
            availability=validated_availability
        )
        
        # Update owner model fields
        current_owner.name = owner_update.name
        current_owner.business_name = owner_update.business_name
        current_owner.phone = owner_update.phone
        current_owner.services_json = json.dumps([s.dict() for s in validated_services])
        current_owner.availability_json = json.dumps([a.dict() for a in validated_availability])
        
        db.add(current_owner)
        db.commit()
        db.refresh(current_owner)

        return RedirectResponse(url="/dashboard?message=profile_updated", status_code=status.HTTP_303_SEE_OTHER)
    except json.JSONDecodeError:
        return RedirectResponse(url="/dashboard?error=invalid_json_format", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        print(f"Error updating profile: {e}")
        return RedirectResponse(url=f"/dashboard?error={e}", status_code=status.HTTP_303_SEE_OTHER)


# Public booking page
@app.get("/{owner_slug}", response_class=HTMLResponse)
async def booking_page(owner_slug: str, request: Request, db: Session = Depends(get_db)):
    _ = get_translator(request)
    env = get_jinja_env(get_locale(request))
    template = env.get_template("booking_page.html")
    
    owner = crud.get_owner_by_slug(db, slug=owner_slug)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Owner not found")

    owner_services = json.loads(owner.services_json) if owner.services_json else []
    owner_availability = json.loads(owner.availability_json) if owner.availability_json else []
    
    return template.render(
        request=request,
        owner=owner,
        services=owner_services,
        availability=owner_availability,
        _=_,
        current_lang=get_locale(request)
    )

@app.post("/{owner_slug}/book", response_class=RedirectResponse)
async def submit_booking(
    owner_slug: str,
    request: Request,
    customer_name: str = Form(...),
    customer_email: str = Form(...),
    customer_phone: Optional[str] = Form(None),
    service_name: str = Form(...),
    booking_date: str = Form(...), # YYYY-MM-DD
    booking_time: str = Form(...), # HH:MM
    db: Session = Depends(get_db)
):
    _ = get_translator(request)
    owner = crud.get_owner_by_slug(db, slug=owner_slug)
    if not owner:
        return RedirectResponse(url=f"/{owner_slug}?error=owner_not_found", status_code=status.HTTP_303_SEE_OTHER)

    try:
        # Combine date and time to create a datetime object
        booking_datetime_str = f"{booking_date} {booking_time}"
        booking_datetime = datetime.datetime.strptime(booking_datetime_str, "%Y-%m-%d %H:%M")

        # Basic validation: ensure booking is in the future
        if booking_datetime < datetime.datetime.now():
            return RedirectResponse(url=f"/{owner_slug}?error=past_booking", status_code=status.HTTP_303_SEE_OTHER)

        booking_in = schemas.BookingCreate(
            customer_name=customer_name,
            customer_email=customer_email,
            customer_phone=customer_phone,
            service_name=service_name,
            booking_time=booking_datetime
        )
        db_booking = crud.create_booking(db=db, booking=booking_in, owner_id=owner.id)

        # Send notifications
        owner_email_subject = _("New Booking Received!")
        owner_email_body = _(f"You have a new booking from {customer_name} for {service_name} at {booking_datetime.strftime('%Y-%m-%d %H:%M')}.")
        if customer_phone:
            owner_email_body += _(f" Customer Phone: {customer_phone}.")
        
        notifications.send_email_notification(owner.email, owner_email_subject, owner_email_body)
        
        customer_email_subject = _(f"Your Booking with {owner.business_name} Confirmed!")
        customer_email_body = _(f"Hi {customer_name}, your booking for {service_name} with {owner.business_name} on {booking_datetime.strftime('%Y-%m-%d %H:%M')} is confirmed.")
        
        notifications.send_email_notification(customer_email, customer_email_subject, customer_email_body)

        if owner.phone and customer_phone: # Only send WhatsApp if owner has phone and customer provided one
             owner_whatsapp_message = _(f"New booking for {owner.business_name}: {customer_name} for {service_name} at {booking_datetime.strftime('%Y-%m-%d %H:%M')}. Customer Phone: {customer_phone}")
             notifications.send_whatsapp_notification(owner.phone, owner_whatsapp_message)
        
        return RedirectResponse(url=f"/{owner_slug}/confirmation", status_code=status.HTTP_303_SEE_OTHER)
    except ValueError as e:
        print(f"Booking error: {e}")
        return RedirectResponse(url=f"/{owner_slug}?error=invalid_booking_time", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        print(f"Error during booking submission: {e}")
        return RedirectResponse(url=f"/{owner_slug}?error=booking_failed", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/{owner_slug}/confirmation", response_class=HTMLResponse)
async def booking_confirmation_page(owner_slug: str, request: Request, db: Session = Depends(get_db)):
    _ = get_translator(request)
    env = get_jinja_env(get_locale(request))
    template = env.get_template("booking_confirmation.html")
    
    owner = crud.get_owner_by_slug(db, slug=owner_slug)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Owner not found")

    return template.render(
        request=request,
        owner=owner,
        _=_,
        current_lang=get_locale(request)
    )
