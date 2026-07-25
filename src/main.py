from fastapi import FastAPI, Depends, HTTPException, status, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from typing import List, Optional
import json
import os

from . import crud, models, schemas, security, notifications
from .database import SessionLocal, engine
from .config import settings
from .i18n_config import get_jinja_env

# Create database tables
models.Base.metadata.create_all(bind=engine)

app = FastAPI()

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Jinja2 Environment for templates
def get_current_locale(request: Request):
    return request.query_params.get('lang', 'en')

# Routes
@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.post("/token", response_model=schemas.Token)
async def login_for_access_token(db: Session = Depends(get_db), form_data: OAuth2PasswordRequestForm = Depends()):
    owner = crud.authenticate_owner(db, form_data.username, form_data.password)
    if not owner:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = security.create_access_token(data={"sub": owner.email})
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/register", response_model=schemas.OwnerInDB)
async def register_owner(owner: schemas.OwnerCreate, db: Session = Depends(get_db)):
    db_owner = crud.get_owner_by_email(db, owner.email)
    if db_owner:
        raise HTTPException(status_code=400, detail="Email already registered")
    db_owner = crud.get_owner_by_slug(db, owner.slug)
    if db_owner:
        raise HTTPException(status_code=400, detail="Business URL slug already taken")
    return crud.create_owner(db=db, owner=owner)

@app.get("/owner/me", response_model=schemas.OwnerInDB)
async def read_owner_me(current_owner: models.Owner = Depends(security.get_current_owner)):
    return current_owner

@app.get("/dashboard", response_class=HTMLResponse)
async def owner_dashboard(request: Request, db: Session = Depends(get_db), current_owner: models.Owner = Depends(security.get_current_owner)):
    locale = get_current_locale(request)
    env = get_jinja_env(locale)
    template = env.get_template("dashboard.html")

    # Parse services and availability from JSON strings
    services_data = json.loads(current_owner.services_json) if current_owner.services_json else []
    availability_data = json.loads(current_owner.availability_json) if current_owner.availability_json else {}

    # Fetch upcoming bookings for the current owner
    upcoming_bookings = db.query(models.Booking).filter(models.Booking.owner_id == current_owner.id).order_by(models.Booking.booking_time).all()

    return template.render(
        request=request,
        owner=current_owner,
        services=services_data,
        availability=availability_data,
        upcoming_bookings=upcoming_bookings,
        current_lang=locale
    )

@app.post("/owner/profile", response_class=HTMLResponse)
async def update_owner_profile_post(
    request: Request,
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(security.get_current_owner),
    name: str = Form(...),
    business_name: str = Form(...),
    phone: Optional[str] = Form(None),
    services_json: str = Form("[]"), # Expecting JSON string
    availability_json: str = Form("{}") # Expecting JSON string
):
    locale = get_current_locale(request)
    env = get_jinja_env(locale)
    template = env.get_template("dashboard.html")
    
    try:
        # Validate services_json and availability_json
        validated_services = json.loads(services_json)
        validated_availability = json.loads(availability_json)

        # Update owner details
        owner_update_schema = schemas.OwnerProfileUpdate(name=name, business_name=business_name, phone=phone)
        updated_owner = crud.update_owner_profile(db, current_owner, owner_update_schema)
        
        # Update services_json and availability_json directly after validation
        updated_owner.services_json = json.dumps(validated_services)
        updated_owner.availability_json = json.dumps(validated_availability)
        db.add(updated_owner)
        db.commit()
        db.refresh(updated_owner)
        
        # Re-fetch upcoming bookings
        upcoming_bookings = db.query(models.Booking).filter(models.Booking.owner_id == updated_owner.id).order_by(models.Booking.booking_time).all()

        return template.render(
            request=request,
            owner=updated_owner,
            services=validated_services,
            availability=validated_availability,
            upcoming_bookings=upcoming_bookings,
            current_lang=locale,
            message="Profile updated successfully!"
        )
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON format for services or availability")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@app.get("/book/{owner_slug}", response_class=HTMLResponse)
async def public_booking_page(owner_slug: str, request: Request, db: Session = Depends(get_db)):
    locale = get_current_locale(request)
    env = get_jinja_env(locale)
    template = env.get_template("booking_page.html")

    owner = crud.get_owner_by_slug(db, owner_slug)
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")
    
    services = json.loads(owner.services_json) if owner.services_json else []
    availability = json.loads(owner.availability_json) if owner.availability_json else {}

    return template.render(
        request=request,
        owner=owner,
        services=services,
        availability=availability,
        current_lang=locale
    )

@app.post("/book/{owner_slug}", response_class=HTMLResponse)
async def submit_booking(
    owner_slug: str,
    request: Request,
    db: Session = Depends(get_db),
    customer_name: str = Form(...),
    customer_email: str = Form(...),
    customer_phone: Optional[str] = Form(None),
    service_name: str = Form(...),
    booking_time: str = Form(...)
):
    locale = get_current_locale(request)
    env = get_jinja_env(locale)

    owner = crud.get_owner_by_slug(db, owner_slug)
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")

    try:
        booking_create = schemas.BookingCreate(
            customer_name=customer_name,
            customer_email=customer_email,
            customer_phone=customer_phone,
            service_name=service_name,
            booking_time=booking_time
        )
        booking = crud.create_booking(db, booking_create, owner.id)

        # Send notifications
        notifications.send_email_notification(
            recipient_email=owner.email,
            subject="New Booking Received!",
            body=f"You have a new booking from {customer_name} for {service_name} at {booking_time}. Customer email: {customer_email}, phone: {customer_phone}"
        )
        notifications.send_email_notification(
            recipient_email=customer_email,
            subject="Your Booking Confirmation",
            body=f"Hi {customer_name}, your booking for {service_name} with {owner.business_name} at {booking_time} is confirmed."
        )
        if owner.phone:
            notifications.send_whatsapp_notification(
                recipient_phone=owner.phone,
                message=f"New BookSlot booking! {customer_name} for {service_name} at {booking_time}. Email: {customer_email}, Phone: {customer_phone}"
            )
        if customer_phone:
            notifications.send_whatsapp_notification(
                recipient_phone=customer_phone,
                message=f"Your BookSlot booking for {service_name} with {owner.business_name} at {booking_time} is confirmed."
            )

        return RedirectResponse(url=f"/booking-confirmation/{owner.slug}?lang={locale}", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        # Log the error for debugging purposes
        print(f"Error during booking submission: {e}")
        # Render the booking page again with an error message
        template = env.get_template("booking_page.html")
        services = json.loads(owner.services_json) if owner.services_json else []
        availability = json.loads(owner.availability_json) if owner.availability_json else {}
        return template.render(
            request=request,
            owner=owner,
            services=services,
            availability=availability,
            current_lang=locale,
            error_message="There was an error processing your booking. Please try again."
        )

@app.get("/booking-confirmation/{owner_slug}", response_class=HTMLResponse)
async def booking_confirmation_page(owner_slug: str, request: Request, db: Session = Depends(get_db)):
    locale = get_current_locale(request)
    env = get_jinja_env(locale)
    template = env.get_template("booking_confirmation.html")

    owner = crud.get_owner_by_slug(db, owner_slug)
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")

    return template.render(
        request=request,
        owner=owner,
        current_lang=locale
    )

# Static files (if needed, typically served by a web server in production)
# from fastapi.staticfiles import StaticFiles
# app.mount("/static", StaticFiles(directory="static"), name="static")
