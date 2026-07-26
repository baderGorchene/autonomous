import json
import datetime
from typing import List, Optional
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

from fastapi import FastAPI, Depends, HTTPException, status, Request, Form, Response
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from pydantic import ValidationError

from . import crud, models, schemas, security
from .database import SessionLocal, engine, Base
from .config import settings
from .notifications import send_email, send_whatsapp_message
from .i18n_config import get_jinja_env, PROJECT_ROOT # Import PROJECT_ROOT

# Create all database tables
Base.metadata.create_all(bind=engine)

app = FastAPI()

# Mount static files
app.mount("/static", StaticFiles(directory=f"{PROJECT_ROOT}/static"), name="static")

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- Helper for i18n Jinja2 Environment ---
def get_jinja_env_with_locale(request: Request):
    locale = request.cookies.get("locale", "en")
    return get_jinja_env(locale)

# --- Routes ---

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request, db: Session = Depends(get_db)):
    current_owner = None
    try:
        token = request.cookies.get("access_token")
        if token:
            current_owner = await security.get_current_owner(token=token, db=db)
    except HTTPException:
        current_owner = None # Token invalid or expired

    env = get_jinja_env_with_locale(request)
    template = env.get_template("index.html") # Assuming an index.html for the root
    return template.render({"request": request, "current_owner": current_owner})

@app.get("/register", response_class=HTMLResponse)
async def get_register(request: Request):
    env = get_jinja_env_with_locale(request)
    template = env.get_template("register.html")
    return template.render({"request": request, "error": None})

@app.post("/register", response_class=HTMLResponse)
async def post_register(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    name: str = Form(...),
    business_name: str = Form(...),
    slug: str = Form(...),
    db: Session = Depends(get_db)
):
    env = get_jinja_env_with_locale(request)
    template = env.get_template("register.html")

    db_owner = crud.get_owner_by_email(db, email=email)
    if db_owner:
        return template.render({"request": request, "error": "Email already registered"})

    db_owner_slug = crud.get_owner_by_slug(db, slug=slug)
    if db_owner_slug:
        return template.render({"request": request, "error": "Business URL slug already taken"})

    try:
        owner = schemas.OwnerCreate(
            email=email, password=password, name=name, business_name=business_name, slug=slug
        )
        crud.create_owner(db=db, owner=owner);
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    except ValidationError as e:
        return template.render({"request": request, "error": f"Validation error: {e.errors()}"})
    except Exception as e:
        return template.render({"request": request, "error": f"An unexpected error occurred: {e}"})

@app.get("/login", response_class=HTMLResponse)
async def get_login(request: Request):
    env = get_jinja_env_with_locale(request)
    template = env.get_template("login.html")
    return template.render({"request": request, "error": None})

@app.post("/login", response_class=HTMLResponse)
async def post_login(
    request: Request,
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    env = get_jinja_env_with_locale(request)
    template = env.get_template("login.html")

    owner = security.authenticate_owner(db, form_data.username, form_data.password)
    if not owner:
        return template.render({"request": request, "error": "Incorrect email or password"})

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": owner.email}, expires_delta=access_token_expires
    )
    response.set_cookie(key="access_token", value=access_token, httponly=True, expires=access_token_expires.total_seconds())
    return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/logout")
async def logout(response: Response):
    response.delete_cookie(key="access_token")
    return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db), current_owner: models.Owner = Depends(security.get_current_owner)):
    env = get_jinja_env_with_locale(request)
    template = env.get_template("dashboard.html")

    upcoming_bookings = db.query(models.Booking).filter(
        models.Booking.owner_id == current_owner.id,
        models.Booking.booking_date >= datetime.date.today()
    ).order_by(models.Booking.booking_date, models.Booking.booking_time).all()

    services = json.loads(current_owner.services_json) if current_owner.services_json else []
    availability = json.loads(current_owner.availability_json) if current_owner.availability_json else {}

    return template.render({
        "request": request,
        "owner": current_owner,
        "upcoming_bookings": upcoming_bookings,
        "services": services,
        "availability": availability,
        "error": None,
        "success": None
    })

@app.post("/dashboard/profile", response_class=HTMLResponse)
async def update_owner_profile(
    request: Request,
    name: str = Form(...),
    business_name: str = Form(...),
    phone: Optional[str] = Form(None),
    services_data: str = Form(..., alias="services"), # Expecting JSON string
    availability_data: str = Form(..., alias="availability"), # Expecting JSON string
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(security.get_current_owner)
):
    env = get_jinja_env_with_locale(request)
    template = env.get_template("dashboard.html")

    services = []
    availability = {}
    error_message = None

    try:
        services = json.loads(services_data)
        # Validate services against schema if needed, e.g., ensure each has 'name', 'duration'
        for service in services:
            schemas.Service(**service) # Validate each service item
    except (json.JSONDecodeError, ValidationError) as e:
        error_message = f"Invalid services data: {e}"

    try:
        availability = json.loads(availability_data)
        # Validate availability against schema if needed
        # Example: ensure keys are days, values are lists of slots with start_time/end_time
        for day, slots in availability.items():
            for slot in slots:
                schemas.AvailabilitySlot(**slot) # Validate each slot item
    except (json.JSONDecodeError, ValidationError) as e:
        if not error_message: # Only set if services didn't already set one
            error_message = f"Invalid availability data: {e}"
        else:
            error_message += f" And invalid availability data: {e}"

    if error_message:
        # Re-fetch bookings for rendering dashboard with error
        upcoming_bookings = db.query(models.Booking).filter(
            models.Booking.owner_id == current_owner.id,
            models.Booking.booking_date >= datetime.date.today()
        ).order_by(models.Booking.booking_date, models.Booking.booking_time).all()
        return template.render({
            "request": request,
            "owner": current_owner,
            "upcoming_bookings": upcoming_bookings,
            "services": services, # Render with potentially invalid data to show user what they entered
            "availability": availability, # Render with potentially invalid data
            "error": error_message,
            "success": None
        })

    try:
        owner_update = schemas.OwnerProfileUpdate(
            name=name,
            business_name=business_name,
            phone=phone if phone else None,
            services=services,
            availability=availability
        )
        # Update owner's basic profile fields
        crud.update_owner_profile(db, current_owner, owner_update)
        # Update services_json and availability_json directly on the model
        current_owner.services_json = json.dumps(services)
        current_owner.availability_json = json.dumps(availability)
        db.add(current_owner)
        db.commit()
        db.refresh(current_owner)

        return RedirectResponse(url="/dashboard?success=Profile updated successfully", status_code=status.HTTP_303_SEE_OTHER)
    except ValidationError as e:
        error_message = f"Validation error: {e.errors()}"
    except Exception as e:
        error_message = f"An unexpected error occurred: {e}"

    # If there was an error during DB update, re-render dashboard with error
    upcoming_bookings = db.query(models.Booking).filter(
        models.Booking.owner_id == current_owner.id,
        models.Booking.booking_date >= datetime.date.today()
    ).order_by(models.Booking.booking_date, models.Booking.booking_time).all()
    return template.render({
        "request": request,
        "owner": current_owner,
        "upcoming_bookings": upcoming_bookings,
        "services": services,
        "availability": availability,
        "error": error_message,
        "success": None
    })

@app.get("/{owner_slug}", response_class=HTMLResponse)
async def get_booking_page(request: Request, owner_slug: str, db: Session = Depends(get_db)):
    owner = crud.get_owner_by_slug(db, slug=owner_slug)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Owner not found")

    env = get_jinja_env_with_locale(request)
    template = env.get_template("booking_page.html")

    services = json.loads(owner.services_json) if owner.services_json else []
    availability = json.loads(owner.availability_json) if owner.availability_json else {}

    # Prepare available time slots (simplified for this example, a real app would calculate based on existing bookings)
    available_slots = {}
    today = datetime.date.today()
    for i in range(7): # Next 7 days
        current_date = today + datetime.timedelta(days=i)
        day_name = current_date.strftime("%A") # e.g., "Monday"
        date_str = current_date.isoformat() # YYYY-MM-DD

        if day_name in availability:
            day_slots = []
            for slot_range in availability[day_name]:
                start_h, start_m = map(int, slot_range['start_time'].split(':'))
                end_h, end_m = map(int, slot_range['end_time'].split(':'))
                
                current_time = datetime.datetime(current_date.year, current_date.month, current_date.day, start_h, start_m)
                end_time_obj = datetime.datetime(current_date.year, current_date.month, current_date.day, end_h, end_m)

                while current_time + datetime.timedelta(minutes=30) <= end_time_obj: # Assume 30 min slots for now
                    if current_date == today and current_time < datetime.datetime.now():
                        # Don't show past slots for today
                        current_time += datetime.timedelta(minutes=30)
                        continue
                    day_slots.append(current_time.strftime("%H:%M"))
                    current_time += datetime.timedelta(minutes=30)
            if day_slots:
                available_slots[date_str] = day_slots

    return template.render({
        "request": request,
        "owner": owner,
        "services": services,
        "available_slots": json.dumps(available_slots), # Pass as JSON string for JS
        "error": None,
        "success": None
    })

@app.post("/{owner_slug}/book", response_class=HTMLResponse)
async def submit_booking(
    request: Request,
    owner_slug: str,
    customer_name: str = Form(...),
    customer_email: str = Form(...),
    customer_phone: Optional[str] = Form(None),
    service_name: str = Form(...),
    booking_date_str: str = Form(..., alias="booking_date"),
    booking_time: str = Form(...),
    notes: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    owner = crud.get_owner_by_slug(db, slug=owner_slug)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Owner not found")

    env = get_jinja_env_with_locale(request)
    booking_page_template = env.get_template("booking_page.html")
    confirmation_template = env.get_template("booking_confirmation.html")

    try:
        booking_date = datetime.datetime.strptime(booking_date_str, "%Y-%m-%d").date()
        # Basic validation for past dates
        if booking_date < datetime.date.today():
            raise ValueError("Cannot book for a past date.")
        # Further validation for time slots within owner's availability would go here
        # For MVP, we assume the selected slot is valid if it came from the UI.

        booking = schemas.BookingCreate(
            customer_name=customer_name,
            customer_email=customer_email,
            customer_phone=customer_phone,
            service_name=service_name,
            booking_date=booking_date,
            booking_time=booking_time,
            notes=notes
        )
        db_booking = crud.create_booking(db=db, booking=booking, owner_id=owner.id)

        # Send notifications
        # Owner notification
        owner_subject = f"New Booking for {service_name} at {booking_time} on {booking_date_str}"
        owner_body = f"""
        <html>
        <body>
            <p>Dear {owner.name},</p>
            <p>You have a new booking!</p>
            <ul>
                <li>Service: {service_name}</li>
                <li>Date: {booking_date_str}</li>
                <li>Time: {booking_time}</li>
                <li>Customer Name: {customer_name}</li>
                <li>Customer Email: {customer_email}</li>
                <li>Customer Phone: {customer_phone if customer_phone else 'N/A'}</li>
                <li>Notes: {notes if notes else 'N/A'}</li>
            </ul>
            <p>Manage your bookings at <a href="{request.url_for('dashboard')}">your dashboard</a>.</p>
        </body>
        </html>
        """
        send_email(owner.email, owner_subject, owner_body)
        if owner.phone:
            whatsapp_owner_msg = f"New BookSlot booking: {service_name} on {booking_date_str} at {booking_time} by {customer_name}. Email: {customer_email}. Phone: {customer_phone if customer_phone else 'N/A'}"
            send_whatsapp_message(owner.phone, whatsapp_owner_msg)

        # Customer notification
        customer_subject = f"Your Booking Confirmation for {service_name} with {owner.business_name}"
        customer_body = f"""
        <html>
        <body>
            <p>Dear {customer_name},</p>
            <p>Your booking with {owner.business_name} has been confirmed!</p>
            <ul>
                <li>Service: {service_name}</li>
                <li>Date: {booking_date_str}</li>
                <li>Time: {booking_time}</li>
                <li>Business: {owner.business_name}</li>
                <li>Contact: {owner.email}{f' / {owner.phone}' if owner.phone else ''}</li>
            </ul>
            <p>We look forward to seeing you!</p>
        </body>
        </html>
        """
        send_email(customer_email, customer_subject, customer_body)
        if customer_phone:
            whatsapp_customer_msg = f"Your BookSlot booking with {owner.business_name} for {service_name} on {booking_date_str} at {booking_time} is confirmed!"
            send_whatsapp_message(customer_phone, whatsapp_customer_msg)

        return confirmation_template.render({
            "request": request,
            "owner": owner,
            "booking": db_booking,
            "success_message": _("Your booking has been successfully confirmed!")
        })

    except ValidationError as e:
        error_message = f"Validation error: {e.errors()}"
    except ValueError as e:
        error_message = f"Booking error: {e}"
    except Exception as e:
        error_message = f"An unexpected error occurred: {e}"

    # If there was an error, re-render the booking page with the error message
    services = json.loads(owner.services_json) if owner.services_json else []
    availability = json.loads(owner.availability_json) if owner.availability_json else {}
    available_slots = {} # Re-calculate or pass empty if error
    today = datetime.date.today()
    for i in range(7): # Next 7 days
        current_date = today + datetime.timedelta(days=i)
        day_name = current_date.strftime("%A") # e.g., "Monday"
        date_str = current_date.isoformat() # YYYY-MM-DD

        if day_name in availability:
            day_slots = []
            for slot_range in availability[day_name]:
                start_h, start_m = map(int, slot_range['start_time'].split(':'))
                end_h, end_m = map(int, slot_range['end_time'].split(':'))
                
                current_time = datetime.datetime(current_date.year, current_date.month, current_date.day, start_h, start_m)
                end_time_obj = datetime.datetime(current_date.year, current_date.month, current_date.day, end_h, end_m)

                while current_time + datetime.timedelta(minutes=30) <= end_time_obj: # Assume 30 min slots for now
                    if current_date == today and current_time < datetime.datetime.now():
                        current_time += datetime.timedelta(minutes=30)
                        continue
                    day_slots.append(current_time.strftime("%H:%M"))
                    current_time += datetime.timedelta(minutes=30)
            if day_slots:
                available_slots[date_str] = day_slots

    return booking_page_template.render({
        "request": request,
        "owner": owner,
        "services": services,
        "available_slots": json.dumps(available_slots),
        "error": error_message,
        "customer_name": customer_name,
        "customer_email": customer_email,
        "customer_phone": customer_phone,
        "service_name": service_name,
        "booking_date_str": booking_date_str,
        "booking_time": booking_time,
        "notes": notes
    })

@app.get("/set_locale/{locale_code}")
async def set_locale(locale_code: str, request: Request, response: Response):
    response = RedirectResponse(url=request.headers.get("referer", "/"), status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(key="locale", value=locale_code, expires=3600*24*30) # 30 days
    return response

# Health check endpoint
@app.get("/health")
async def health_check():
    return {"status": "ok"}
