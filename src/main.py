from fastapi import FastAPI, Depends, HTTPException, status, Request, Response, Form
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import json
import os
from datetime import date, datetime, timedelta
import calendar
from typing import List, Optional
import re

from . import crud, models, schemas, security, notifications, config
from .database import SessionLocal, engine
from .i18n_config import get_jinja_env

# Ensure all models are imported before creating tables
models.Base.metadata.create_all(bind=engine)

app = FastAPI()

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Setup Jinja2Templates with i18n support
jinja_env = get_jinja_env()
templates = Jinja2Templates(directory="templates", env=jinja_env)

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Helper to get current locale
def get_locale(request: Request) -> str:
    return request.cookies.get("locale", "en")

@app.on_event("startup")
async def startup_event():
    # This ensures tables are created on startup if they don't exist
    # It's already called above, but good to have in startup for explicit clarity.
    pass

@app.get("/health", tags=["Health Check"])
async def health_check():
    return {"status": "ok"}

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def root(request: Request, db: Session = Depends(get_db)):
    access_token = request.cookies.get("access_token")
    if access_token:
        try:
            current_owner = await security.get_current_owner(access_token, db)
            if current_owner:
                return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
        except HTTPException:
            pass # Token invalid, proceed to login
    return templates.TemplateResponse("login.html", {"request": request, "locale": get_locale(request)})

# --- Authentication and Owner Management (UI) ---
@app.get("/signup", response_class=HTMLResponse, tags=["Auth UI"])
async def signup_form(request: Request):
    return templates.TemplateResponse("signup.html", {"request": request, "locale": get_locale(request)})

@app.post("/signup", response_class=HTMLResponse, tags=["Auth UI"])
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
    owner = crud.get_owner_by_email(db, email=email)
    if owner:
        return templates.TemplateResponse("signup.html", {"request": request, "error": "Email already registered", "locale": get_locale(request)} , status_code=status.HTTP_400_BAD_REQUEST)
    owner = crud.get_owner_by_slug(db, slug=slug)
    if owner:
        return templates.TemplateResponse("signup.html", {"request": request, "error": "Business URL already taken", "locale": get_locale(request)} , status_code=status.HTTP_400_BAD_REQUEST)
    
    try:
        owner_create = schemas.OwnerCreate(name=name, email=email, password=password, business_name=business_name, slug=slug, phone=phone)
        crud.create_owner(db=db, owner=owner_create)
        return templates.TemplateResponse("login.html", {"request": request, "message": "Account created successfully! Please log in.", "locale": get_locale(request)})
    except Exception as e:
        return templates.TemplateResponse("signup.html", {"request": request, "error": f"An error occurred: {e}", "locale": get_locale(request)} , status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

@app.get("/login", response_class=HTMLResponse, tags=["Auth UI"])
async def login_form(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "locale": get_locale(request)})

@app.post("/login", response_class=HTMLResponse, tags=["Auth UI"])
async def login_for_access_token(
    request: Request,
    db: Session = Depends(get_db),
    email: str = Form(...),
    password: str = Form(...)
):
    owner = crud.authenticate_owner(db, email, password)
    if not owner:
        return templates.TemplateResponse("login.html", {"request": request, "error": "Incorrect email or password", "locale": get_locale(request)} , status_code=status.HTTP_401_UNAUTHORIZED)
    access_token = security.create_access_token(data={"sub": owner.email})
    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    response.set_cookie(key="access_token", value=access_token, httponly=True, samesite="Lax")
    return response

@app.get("/logout", tags=["Auth UI"])
async def logout(response: Response):
    response = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    response.delete_cookie(key="access_token")
    return response

# --- Owner Dashboard and Profile (UI) ---
@app.get("/dashboard", response_class=HTMLResponse, tags=["Owner UI"])
async def owner_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(security.get_current_owner)
):
    bookings = crud.get_owner_bookings(db, current_owner.id)
    return templates.TemplateResponse("dashboard.html", {"request": request, "owner": current_owner, "bookings": bookings, "locale": get_locale(request)})

@app.get("/profile", response_class=HTMLResponse, tags=["Owner UI"])
async def owner_profile(
    request: Request,
    current_owner: models.Owner = Depends(security.get_current_owner)
):
    services = json.loads(current_owner.services_json) if current_owner.services_json else []
    availability = json.loads(current_owner.availability_json) if current_owner.availability_json else []
    return templates.TemplateResponse("profile.html", {"request": request, "owner": current_owner, "services": services, "availability": availability, "locale": get_locale(request)})

@app.post("/profile", response_class=HTMLResponse, tags=["Owner UI"])
async def update_owner_profile_post(
    request: Request,
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(security.get_current_owner),
    name: str = Form(...),
    business_name: str = Form(...),
    phone: Optional[str] = Form(None),
    services_data: str = Form("[]"), # JSON string
    availability_data: str = Form("{}") # JSON string
):
    try:
        # Validate and parse services
        parsed_services = json.loads(services_data)
        validated_services = [schemas.Service(**s) for s in parsed_services]
        current_owner.services_json = json.dumps([s.dict() for s in validated_services])

        # Validate and parse availability
        parsed_availability = json.loads(availability_data)
        validated_availability = [schemas.AvailabilitySlot(**a) for a in parsed_availability]
        current_owner.availability_json = json.dumps([a.dict() for a in validated_availability])

        owner_update_schema = schemas.OwnerProfileUpdate(name=name, business_name=business_name, phone=phone, services=validated_services, availability=validated_availability)
        updated_owner = crud.update_owner_profile(db, current_owner, owner_update_schema)
        return templates.TemplateResponse("profile.html", {"request": request, "owner": updated_owner, "services": validated_services, "availability": validated_availability, "message": "Profile updated successfully!", "locale": get_locale(request)})
    except json.JSONDecodeError:
        return templates.TemplateResponse("profile.html", {"request": request, "owner": current_owner, "error": "Invalid JSON for services or availability.", "locale": get_locale(request)}, status_code=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return templates.TemplateResponse("profile.html", {"request": request, "owner": current_owner, "error": f"An error occurred: {e}", "locale": get_locale(request)}, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

# --- Public Booking Page ---
@app.get("/book/{owner_slug}", response_class=HTMLResponse, tags=["Public Booking"])
async def booking_page(
    request: Request,
    owner_slug: str,
    db: Session = Depends(get_db)
):
    owner = crud.get_owner_by_slug(db, slug=owner_slug)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Owner not found")

    services = json.loads(owner.services_json) if owner.services_json else []
    availability_slots = json.loads(owner.availability_json) if owner.availability_json else []

    # Generate available dates (e.g., next 30 days)
    available_dates = []
    today = date.today()
    for i in range(30):
        current_date = today + timedelta(days=i);
        day_of_week = current_date.weekday() # Monday is 0, Sunday is 6
        
        # Check if the owner has availability for this day of the week
        has_availability_for_day = any(slot.get('day_of_week') == day_of_week for slot in availability_slots)
        
        if has_availability_for_day:
            available_dates.append({
                "date": current_date.strftime("%Y-%m-%d"),
                "day_name": calendar.day_name[day_of_week]
            })

    return templates.TemplateResponse(
        "booking_page.html",
        {
            "request": request,
            "owner": owner,
            "services": services,
            "availability_slots": availability_slots,
            "available_dates": available_dates,
            "locale": get_locale(request)
        }
    )

@app.post("/book/{owner_slug}/submit", response_class=HTMLResponse, tags=["Public Booking"])
async def submit_booking(
    request: Request,
    owner_slug: str,
    db: Session = Depends(get_db),
    customer_name: str = Form(...),
    customer_email: str = Form(...),
    customer_phone: Optional[str] = Form(None),
    service_name: str = Form(...),
    booking_date: str = Form(...),
    booking_time: str = Form(...)
):
    owner = crud.get_owner_by_slug(db, slug=owner_slug)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Owner not found")

    # Basic validation for date and time format
    try:
        datetime.strptime(booking_date, "%Y-%m-%d")
        datetime.strptime(booking_time, "%H:%M")
    except ValueError:
        return templates.TemplateResponse(
            "booking_page.html",
            {
                "request": request,
                "owner": owner,
                "services": json.loads(owner.services_json),
                "availability_slots": json.loads(owner.availability_json),
                "error": "Invalid date or time format.",
                "locale": get_locale(request)
            },
            status_code=status.HTTP_400_BAD_REQUEST
        )
    
    # Further validation: check if the selected service exists for this owner
    services = json.loads(owner.services_json) if owner.services_json else []
    if not any(s['name'] == service_name for s in services):
         return templates.TemplateResponse(
            "booking_page.html",
            {
                "request": request,
                "owner": owner,
                "services": json.loads(owner.services_json),
                "availability_slots": json.loads(owner.availability_json),
                "error": "Selected service is not available.",
                "locale": get_locale(request)
            },
            status_code=status.HTTP_400_BAD_REQUEST
        )

    # Further validation: check if the selected time slot is available based on owner's availability_json
    # This is a simplified check. A robust system would check for overlaps with existing bookings too.
    booking_datetime_obj = datetime.strptime(f"{booking_date} {booking_time}", "%Y-%m-%d %H:%M")
    requested_day_of_week = booking_datetime_obj.weekday()
    requested_time_str = booking_datetime_obj.strftime("%H:%M")

    availability_slots = json.loads(owner.availability_json) if owner.availability_json else []
    is_time_slot_valid = False
    for slot in availability_slots:
        if slot['day_of_week'] == requested_day_of_week:
            start_time = datetime.strptime(slot['start_time'], "%H:%M").time()
            end_time = datetime.strptime(slot['end_time'], "%H:%M").time()
            requested_time = booking_datetime_obj.time()
            if start_time <= requested_time < end_time: # Booking must start within the slot
                is_time_slot_valid = True
                break
    
    if not is_time_slot_valid:
        return templates.TemplateResponse(
            "booking_page.html",
            {
                "request": request,
                "owner": owner,
                "services": json.loads(owner.services_json),
                "availability_slots": json.loads(owner.availability_json),
                "error": "Selected time slot is not available or outside business hours.",
                "locale": get_locale(request)
            },
            status_code=status.HTTP_400_BAD_REQUEST
        )

    try:
        booking_create = schemas.BookingCreate(
            customer_name=customer_name,
            customer_email=customer_email,
            customer_phone=customer_phone,
            service_name=service_name,
            booking_date=booking_date,
            booking_time=booking_time
        )
        crud.create_booking(db=db, booking=booking_create, owner_id=owner.id)

        booking_details_for_notification = {
            "business_name": owner.business_name,
            "owner_name": owner.name,
            "service_name": service_name,
            "booking_date": booking_date,
            "booking_time": booking_time,
            "customer_name": customer_name,
            "customer_email": customer_email,
            "customer_phone": customer_phone
        }
        notifications.send_booking_confirmation(
            booking_details_for_notification,
            owner.email,
            owner.phone,
            customer_email,
            customer_phone,
            locale=get_locale(request)
        )

        return RedirectResponse(url="/booking-confirmation", status_code=status.HTTP_302_FOUND)
    except Exception as e:
        # Log the error for debugging
        print(f"Error submitting booking: {e}")
        return templates.TemplateResponse(
            "booking_page.html",
            {
                "request": request,
                "owner": owner,
                "services": json.loads(owner.services_json),
                "availability_slots": json.loads(owner.availability_json),
                "error": f"An unexpected error occurred during booking. Please try again. ({e})",
                "locale": get_locale(request)
            },
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@app.get("/booking-confirmation", response_class=HTMLResponse, tags=["Public Booking"])
async def booking_confirmation(request: Request):
    return templates.TemplateResponse("booking_confirmation.html", {"request": request, "locale": get_locale(request)})

@app.get("/set-locale/{locale_code}", tags=["Internationalization"])
async def set_locale(locale_code: str, response: Response, request: Request):
    response.set_cookie(key="locale", value=locale_code, httponly=False, samesite="Lax")
    # Redirect back to the referrer or a default page
    referrer = request.headers.get("referer", "/")
    return RedirectResponse(url=referrer, status_code=status.HTTP_302_FOUND)

