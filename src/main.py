from fastapi import FastAPI, Depends, HTTPException, status, Request, Response, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from jose import JWTError
from datetime import timedelta, datetime
import json
from typing import List, Dict, Any, Optional
import os

from . import crud, models, schemas, security, notifications
from .database import SessionLocal, engine
from .config import settings
from .i18n_config import get_jinja_env

# Create database tables
models.Base.metadata.create_all(bind=engine)

app = FastAPI()

# OAuth2PasswordBearer for token authentication
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Dependency to get the DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Dependency to get the current owner
async def get_current_owner(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token_data = security.decode_access_token(token)
    if token_data is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    owner = crud.get_owner_by_email(db, email=token_data.email)
    if owner is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not find owner",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return owner

# Helper to get Jinja2 environment with locale
def get_jinja_env_with_locale(request: Request):
    locale = request.cookies.get("lang", "en")
    return get_jinja_env(locale=locale)

# --- Public Routes ---

@app.get("/health", status_code=status.HTTP_200_OK)
async def health_check():
    return {"status": "ok"}

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    env = get_jinja_env_with_locale(request)
    template = env.get_template("index.html") # Assuming an index.html for the landing page
    return template.render(request=request)

@app.get("/signup", response_class=HTMLResponse)
async def signup_form(request: Request):
    env = get_jinja_env_with_locale(request)
    template = env.get_template("signup.html")
    return template.render(request=request, error=None)

@app.post("/signup", response_class=HTMLResponse)
async def signup_owner(request: Request, db: Session = Depends(get_db),
                       name: str = Form(...), email: str = Form(...), password: str = Form(...),
                       business_name: str = Form(...), slug: str = Form(...)):
    env = get_jinja_env_with_locale(request)
    owner = crud.get_owner_by_email(db, email=email)
    if owner:
        template = env.get_template("signup.html")
        return template.render(request=request, error=env.gettext("Email already registered"))
    owner = crud.get_owner_by_slug(db, slug=slug)
    if owner:
        template = env.get_template("signup.html")
        return template.render(request=request, error=env.gettext("Business URL slug already taken"))

    try:
        owner_create = schemas.OwnerCreate(name=name, email=email, password=password, business_name=business_name, slug=slug)
        db_owner = crud.create_owner(db=db, owner=owner_create)
        
        # Auto-login after signup
        access_token_expires = timedelta(minutes=security.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = security.create_access_token(
            data={"sub": db_owner.email},
            expires_delta=access_token_expires
        )
        response = RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
        response.set_cookie(key="access_token", value=access_token, httponly=True, expires=access_token_expires.total_seconds())
        return response
    except Exception as e:
        template = env.get_template("signup.html")
        return template.render(request=request, error=env.gettext(f"Error during signup: {e}"))

@app.get("/login", response_class=HTMLResponse)
async def login_form(request: Request):
    env = get_jinja_env_with_locale(request)
    template = env.get_template("login.html")
    return template.render(request=request, error=None)

@app.post("/login", response_class=HTMLResponse)
async def login_owner(request: Request, db: Session = Depends(get_db),
                      email: str = Form(...), password: str = Form(...)):
    env = get_jinja_env_with_locale(request)
    owner = crud.authenticate_owner(db, email=email, password=password)
    if not owner:
        template = env.get_template("login.html")
        return template.render(request=request, error=env.gettext("Incorrect email or password"))
    access_token_expires = timedelta(minutes=security.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": owner.email},
        expires_delta=access_token_expires
    )
    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    response.set_cookie(key="access_token", value=access_token, httponly=True, expires=access_token_expires.total_seconds())
    return response

@app.post("/logout")
async def logout_owner():
    response = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    response.delete_cookie(key="access_token")
    return response

@app.get("/{owner_slug}", response_class=HTMLResponse)
async def public_booking_page(request: Request, owner_slug: str, db: Session = Depends(get_db)):
    env = get_jinja_env_with_locale(request)
    owner = crud.get_owner_by_slug(db, slug=owner_slug)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Owner not found")

    services = json.loads(owner.services_json) if owner.services_json else []
    availability = json.loads(owner.availability_json) if owner.availability_json else {}

    # Generate available slots (simplified for example)
    # In a real app, this would be more complex, checking existing bookings, etc.
    available_slots = []
    today = datetime.now().date()
    for i in range(7): # Next 7 days
        current_date = today + timedelta(days=i)
        day_of_week = current_date.weekday() # Monday is 0
        
        if str(day_of_week) in availability:
            for slot_range in availability[str(day_of_week)]:
                start_h, start_m = map(int, slot_range['start_time'].split(':'))
                end_h, end_m = map(int, slot_range['end_time'].split(':'))
                
                start_dt = datetime.combine(current_date, datetime.min.time()).replace(hour=start_h, minute=start_m)
                end_dt = datetime.combine(current_date, datetime.min.time()).replace(hour=end_h, minute=end_m)

                # Break down into 30-min slots, check against service durations
                current_slot_start = start_dt
                while current_slot_start + timedelta(minutes=30) <= end_dt:
                    # For simplicity, assume all services are 30min or multiples.
                    # A real system would need to check if a service *fits* here.
                    available_slots.append({
                        "date": current_date.strftime("%Y-%m-%d"),
                        "time": current_slot_start.strftime("%H:%M")
                    })
                    current_slot_start += timedelta(minutes=30)

    template = env.get_template("booking_page.html")
    return template.render(
        request=request,
        owner=owner,
        services=services,
        available_slots=available_slots,
        error=None
    )

@app.post("/{owner_slug}/book", response_class=HTMLResponse)
async def submit_booking(request: Request, owner_slug: str, db: Session = Depends(get_db),
                         customer_name: str = Form(...), customer_email: str = Form(...),
                         customer_phone: Optional[str] = Form(None),
                         service_name: str = Form(...), booking_date: str = Form(...),
                         booking_time: str = Form(...)):
    env = get_jinja_env_with_locale(request)
    owner = crud.get_owner_by_slug(db, slug=owner_slug)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Owner not found")

    try:
        booking_datetime_str = f"{booking_date} {booking_time}"
        booking_datetime = datetime.strptime(booking_datetime_str, "%Y-%m-%d %H:%M")
        
        # Basic validation: booking time must be in the future
        if booking_datetime <= datetime.now():
            template = env.get_template("booking_page.html")
            services = json.loads(owner.services_json) if owner.services_json else []
            availability = json.loads(owner.availability_json) if owner.availability_json else {}
            # Re-generate available_slots for error page
            available_slots = [] # Simplified
            return template.render(request=request, owner=owner, services=services, available_slots=available_slots, error=env.gettext("Booking time must be in the future."))

        booking_create = schemas.BookingCreate(
            customer_name=customer_name,
            customer_email=customer_email,
            customer_phone=customer_phone,
            service_name=service_name,
            booking_time=booking_datetime
        )
        db_booking = crud.create_booking(db=db, booking=booking_create, owner_id=owner.id)

        # Send notifications
        # To owner
        owner_subject = env.gettext("New Booking Received!")
        owner_html = env.gettext(f"Dear {owner.name},<br><br>You have received a new booking:<br>Customer: {customer_name}<br>Email: {customer_email}<br>Phone: {customer_phone or 'N/A'}<br>Service: {service_name}<br>Time: {booking_datetime.strftime('%Y-%m-%d %H:%M')}<br><br>Thank you.<br>BookSlot")
        notifications.send_email_notification(owner.email, owner_subject, owner_html)
        if owner.phone:
            owner_whatsapp_msg = env.gettext(f"BookSlot: New booking for {service_name} at {booking_datetime.strftime('%H:%M')} on {booking_datetime.strftime('%Y-%m-%d')}. Customer: {customer_name}.")
            notifications.send_whatsapp_notification(owner.phone, owner_whatsapp_msg)

        # To customer
        customer_subject = env.gettext("Your Booking Confirmation")
        customer_html = env.gettext(f"Dear {customer_name},<br><br>Your booking for {service_name} with {owner.business_name} on {booking_datetime.strftime('%Y-%m-%d')} at {booking_datetime.strftime('%H:%M')} has been confirmed.<br><br>Thank you for using BookSlot.<br>")
        notifications.send_email_notification(customer_email, customer_subject, customer_html)
        if customer_phone:
            customer_whatsapp_msg = env.gettext(f"Your booking with {owner.business_name} for {service_name} on {booking_datetime.strftime('%Y-%m-%d')} at {booking_datetime.strftime('%H:%M')} is confirmed. BookSlot")
            notifications.send_whatsapp_notification(customer_phone, customer_whatsapp_msg)

        template = env.get_template("booking_confirmation.html")
        return template.render(request=request, owner=owner, booking=db_booking, success=env.gettext("Booking successful!"))
    except ValueError:
        template = env.get_template("booking_page.html")
        services = json.loads(owner.services_json) if owner.services_json else []
        availability = json.loads(owner.availability_json) if owner.availability_json else {}
        available_slots = [] # Simplified
        return template.render(request=request, owner=owner, services=services, available_slots=available_slots, error=env.gettext("Invalid date or time format."))
    except Exception as e:
        template = env.get_template("booking_page.html")
        services = json.loads(owner.services_json) if owner.services_json else []
        availability = json.loads(owner.availability_json) if owner.availability_json else {}
        available_slots = [] # Simplified
        return template.render(request=request, owner=owner, services=services, available_slots=available_slots, error=env.gettext(f"An error occurred during booking: {e}"))

# --- Authenticated Owner Routes ---

@app.get("/dashboard", response_class=HTMLResponse)
async def owner_dashboard(request: Request, current_owner: models.Owner = Depends(get_current_owner), db: Session = Depends(get_db)):
    env = get_jinja_env_with_locale(request)
    # Get upcoming bookings for the owner
    upcoming_bookings = db.query(models.Booking).filter(
        models.Booking.owner_id == current_owner.id,
        models.Booking.booking_time >= datetime.now()
    ).order_by(models.Booking.booking_time).all()

    template = env.get_template("dashboard.html")
    return template.render(request=request, owner=current_owner, bookings=upcoming_bookings)

@app.get("/profile", response_class=HTMLResponse)
async def owner_profile(request: Request, current_owner: models.Owner = Depends(get_current_owner)):
    env = get_jinja_env_with_locale(request)
    template = env.get_template("profile.html")
    return template.render(request=request, owner=current_owner, error=None, success=None)

@app.post("/profile", response_class=HTMLResponse)
async def update_owner_profile(request: Request, current_owner: models.Owner = Depends(get_current_owner),
                               db: Session = Depends(get_db),
                               name: str = Form(...), business_name: str = Form(...), phone: Optional[str] = Form(None)):
    env = get_jinja_env_with_locale(request)
    try:
        owner_update = schemas.OwnerProfileUpdate(name=name, business_name=business_name, phone=phone)
        updated_owner = crud.update_owner_profile(db, current_owner, owner_update)
        template = env.get_template("profile.html")
        return template.render(request=request, owner=updated_owner, success=env.gettext("Profile updated successfully!"), error=None)
    except Exception as e:
        template = env.get_template("profile.html")
        return template.render(request=request, owner=current_owner, error=env.gettext(f"Error updating profile: {e}"), success=None)

@app.get("/services", response_class=HTMLResponse)
async def owner_services(request: Request, current_owner: models.Owner = Depends(get_current_owner)):
    env = get_jinja_env_with_locale(request)
    services = json.loads(current_owner.services_json) if current_owner.services_json else []
    template = env.get_template("services.html")
    return template.render(request=request, owner=current_owner, services=services, error=None)

@app.post("/services", response_class=HTMLResponse)
async def update_owner_services(request: Request, current_owner: models.Owner = Depends(get_current_owner),
                                db: Session = Depends(get_db), services_data: str = Form(...)):
    env = get_jinja_env_with_locale(request)
    try:
        # services_data is expected to be a JSON string of a list of service objects
        services_list = json.loads(services_data)
        # Basic validation for services_list structure
        for service in services_list:
            schemas.Service(**service) # Validate each service item

        current_owner.services_json = json.dumps(services_list)
        db.add(current_owner)
        db.commit()
        db.refresh(current_owner)
        services = json.loads(current_owner.services_json) if current_owner.services_json else []
        template = env.get_template("services.html")
        return template.render(request=request, owner=current_owner, services=services, success=env.gettext("Services updated successfully!"), error=None)
    except json.JSONDecodeError:
        template = env.get_template("services.html")
        services = json.loads(current_owner.services_json) if current_owner.services_json else []
        return template.render(request=request, owner=current_owner, services=services, error=env.gettext("Invalid JSON format for services."))
    except Exception as e:
        template = env.get_template("services.html")
        services = json.loads(current_owner.services_json) if current_owner.services_json else []
        return template.render(request=request, owner=current_owner, services=services, error=env.gettext(f"Error updating services: {e}"))

@app.get("/availability", response_class=HTMLResponse)
async def owner_availability(request: Request, current_owner: models.Owner = Depends(get_current_owner)):
    env = get_jinja_env_with_locale(request)
    availability = json.loads(current_owner.availability_json) if current_owner.availability_json else {}
    template = env.get_template("availability.html")
    return template.render(request=request, owner=current_owner, availability=availability, error=None)

@app.post("/availability", response_class=HTMLResponse)
async def update_owner_availability(request: Request, current_owner: models.Owner = Depends(get_current_owner),
                                   db: Session = Depends(get_db), availability_data: str = Form(...)):
    env = get_jinja_env_with_locale(request)
    try:
        # availability_data is expected to be a JSON string of a dict where keys are day_of_week (0-6) and values are lists of slots
        availability_dict = json.loads(availability_data)
        # Basic validation for availability_dict structure (optional, can be more rigorous)
        # For example, ensure start_time < end_time
        for day, slots in availability_dict.items():
            for slot in slots:
                schemas.AvailabilitySlot(**slot) # Validate each slot item

        current_owner.availability_json = json.dumps(availability_dict)
        db.add(current_owner)
        db.commit()
        db.refresh(current_owner)
        availability = json.loads(current_owner.availability_json) if current_owner.availability_json else {}
        template = env.get_template("availability.html")
        return template.render(request=request, owner=current_owner, availability=availability, success=env.gettext("Availability updated successfully!"), error=None)
    except json.JSONDecodeError:
        template = env.get_template("availability.html")
        availability = json.loads(current_owner.availability_json) if current_owner.availability_json else {}
        return template.render(request=request, owner=current_owner, availability=availability, error=env.gettext("Invalid JSON format for availability."))
    except Exception as e:
        template = env.get_template("availability.html")
        availability = json.loads(current_owner.availability_json) if current_owner.availability_json else {}
        return template.render(request=request, owner=current_owner, availability=availability, error=env.gettext(f"Error updating availability: {e}"))

@app.post("/set-language")
async def set_language(request: Request, lang: str = Form(...)):
    response = RedirectResponse(url=request.headers.get("Referer", "/"), status_code=status.HTTP_302_FOUND)
    response.set_cookie(key="lang", value=lang, httponly=False) # httponly=False for JS access if needed
    return response
