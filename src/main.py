from fastapi import FastAPI, Depends, HTTPException, status, Request, Form, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta
from typing import List, Dict, Any, Optional
import json
import os
from starlette.middleware.sessions import SessionMiddleware
from starlette.datastructures import URL
from starlette.templating import Jinja2Templates

from . import crud, models, schemas, security, notifications
from .database import SessionLocal, engine
from .config import settings
from .i18n_config import get_jinja_env # Import the configured Jinja2 environment

# Create all database tables
models.Base.metadata.create_all(bind=engine)

app = FastAPI()

# Add Session Middleware for language selection
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Dependency to get current owner
async def get_current_owner(request: Request, db: Session = Depends(get_db)):
    token = request.session.get("token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    email = security.decode_access_token(token)
    if email is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    owner = crud.get_owner_by_email(db, email=email)
    if owner is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Owner not found")
    return owner

# Helper to get Jinja2 environment with correct locale
def get_templates(request: Request):
    locale = request.session.get("locale", "en")
    return get_jinja_env(locale)

@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "ok"}

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request, db: Session = Depends(get_db)):
    # Check if owner is logged in
    current_owner = None
    try:
        current_owner = await get_current_owner(request, db)
    except HTTPException:
        pass # Not logged in, render public page or login

    if current_owner:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    
    templates = get_templates(request)
    return templates.get_template("login.html").render({"request": request})

@app.get("/signup", response_class=HTMLResponse)
async def signup_form(request: Request):
    templates = get_templates(request)
    return templates.get_template("owner_signup.html").render({"request": request})

@app.post("/signup", response_class=HTMLResponse)
async def owner_signup(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    business_name: str = Form(...),
    slug: str = Form(...),
    phone: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    templates = get_templates(request)
    owner = crud.get_owner_by_email(db, email=email)
    if owner:
        return templates.get_template("owner_signup.html").render({
            "request": request,
            "error": "Email already registered"
        })
    owner = crud.get_owner_by_slug(db, slug=slug)
    if owner:
        return templates.get_template("owner_signup.html").render({
            "request": request,
            "error": "Business URL already taken"
        })

    try:
        owner_in = schemas.OwnerCreate(
            name=name, email=email, password=password, business_name=business_name, slug=slug, phone=phone
        )
        db_owner = crud.create_owner(db=db, owner=owner_in)
        
        # Log in the user automatically after signup
        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = security.create_access_token(
            data={"sub": db_owner.email}, expires_delta=access_token_expires
        )
        response = RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
        request.session["token"] = access_token
        return response
    except Exception as e:
        return templates.get_template("owner_signup.html").render({
            "request": request,
            "error": f"An error occurred: {e}"
        })

@app.get("/login", response_class=HTMLResponse)
async def login_form(request: Request):
    templates = get_templates(request)
    return templates.get_template("login.html").render({"request": request})

@app.post("/login", response_class=HTMLResponse)
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    templates = get_templates(request)
    owner = crud.authenticate_owner(db, email, password)
    if not owner:
        return templates.get_template("login.html").render({
            "request": request,
            "error": "Incorrect email or password"
        })
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": owner.email}, expires_delta=access_token_expires
    )
    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    request.session["token"] = access_token
    return response

@app.get("/logout")
async def logout(request: Request):
    request.session.pop("token", None)
    return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

@app.get("/dashboard", response_class=HTMLResponse)
async def owner_dashboard(request: Request, db: Session = Depends(get_db), current_owner: models.Owner = Depends(get_current_owner)):
    templates = get_templates(request)
    # Fetch bookings for the current owner
    bookings = db.query(models.Booking).filter(models.Booking.owner_id == current_owner.id).order_by(models.Booking.booking_date, models.Booking.booking_time).all()
    
    # Parse services and availability
    services = json.loads(current_owner.services_json) if current_owner.services_json else []
    availability = json.loads(current_owner.availability_json) if current_owner.availability_json else {}

    return templates.get_template("dashboard.html").render({
        "request": request,
        "owner": current_owner,
        "bookings": bookings,
        "services": services,
        "availability": availability,
        "bookslot_link": f"{request.url.scheme}://{request.url.netloc}/bookslot/{current_owner.slug}"
    })

@app.get("/profile", response_class=HTMLResponse)
async def owner_profile_view(request: Request, current_owner: models.Owner = Depends(get_current_owner)):
    templates = get_templates(request)
    services = json.loads(current_owner.services_json) if current_owner.services_json else []
    availability = json.loads(current_owner.availability_json) if current_owner.availability_json else {}
    return templates.get_template("profile.html").render({
        "request": request,
        "owner": current_owner,
        "services": services,
        "availability": availability
    })

@app.post("/profile", response_class=HTMLResponse)
async def owner_profile_update(
    request: Request,
    name: str = Form(...),
    business_name: str = Form(...),
    phone: Optional[str] = Form(None),
    services_data: str = Form("[]"), # JSON string
    availability_data: str = Form("{}"), # JSON string
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(get_current_owner)
):
    templates = get_templates(request)
    try:
        # Validate services_data and availability_data
        parsed_services = json.loads(services_data)
        parsed_availability = json.loads(availability_data)

        # Basic validation for services
        for service in parsed_services:
            schemas.ServiceCreate(**service) # Validate against schema

        # Basic validation for availability
        for day, slots in parsed_availability.items():
            for slot in slots:
                schemas.AvailabilitySlot(**slot) # Validate against schema

        owner_update_schema = schemas.OwnerProfileUpdate(
            name=name,
            email=current_owner.email, # Email is not updated via this form
            business_name=business_name,
            slug=current_owner.slug, # Slug is not updated via this form
            phone=phone,
            services=parsed_services, # These are validated but not passed to crud directly
            availability=parsed_availability # These are validated but not passed to crud directly
        )
        
        updated_owner = crud.update_owner_profile(db, current_owner, owner_update_schema)
        updated_owner.services_json = services_data
        updated_owner.availability_json = availability_data
        db.add(updated_owner)
        db.commit()
        db.refresh(updated_owner)

        return RedirectResponse(url="/dashboard?message=Profile updated successfully", status_code=status.HTTP_302_FOUND)
    except json.JSONDecodeError:
        return templates.get_template("profile.html").render({
            "request": request,
            "owner": current_owner,
            "error": "Invalid JSON for services or availability.",
            "services": json.loads(services_data),
            "availability": json.loads(availability_data)
        })
    except Exception as e:
        return templates.get_template("profile.html").render({
            "request": request,
            "owner": current_owner,
            "error": f"An error occurred: {e}",
            "services": json.loads(services_data),
            "availability": json.loads(availability_data)
        })

@app.get("/bookslot/{owner_slug}", response_class=HTMLResponse)
async def public_booking_page(request: Request, owner_slug: str, db: Session = Depends(get_db)):
    templates = get_templates(request)
    owner = crud.get_owner_by_slug(db, slug=owner_slug)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking page not found")

    services = json.loads(owner.services_json) if owner.services_json else []
    availability = json.loads(owner.availability_json) if owner.availability_json else {}

    return templates.get_template("booking_page.html").render({
        "request": request,
        "owner": owner,
        "services": services,
        "availability": availability
    })

@app.post("/bookslot/{owner_slug}", response_class=HTMLResponse)
async def submit_booking(
    request: Request,
    owner_slug: str,
    customer_name: str = Form(...),
    customer_email: str = Form(...),
    customer_phone: Optional[str] = Form(None),
    service_name: str = Form(...),
    booking_date: str = Form(...),
    booking_time: str = Form(...),
    db: Session = Depends(get_db)
):
    templates = get_templates(request)
    owner = crud.get_owner_by_slug(db, slug=owner_slug)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking page not found")

    try:
        booking_data = schemas.BookingCreate(
            customer_name=customer_name,
            customer_email=customer_email,
            customer_phone=customer_phone,
            service_name=service_name,
            booking_date=booking_date,
            booking_time=booking_time
        )
        db_booking = crud.create_booking(db=db, booking=booking_data, owner_id=owner.id)

        # Send notifications
        booking_details_dict = booking_data.dict()
        booking_details_dict['business_name'] = owner.business_name

        # Email to Owner
        owner_email_content = notifications.get_owner_booking_confirmation_email_content(owner.name, booking_details_dict)
        notifications.send_email(owner.email, "New Booking Received!", owner_email_content)
        
        # Email to Customer
        customer_email_content = notifications.get_customer_booking_confirmation_email_content(customer_name, owner.business_name, booking_details_dict)
        notifications.send_email(customer_email, "Your Booking Confirmation", customer_email_content)

        # WhatsApp to Owner (if phone is provided)
        if owner.phone:
            owner_whatsapp_content = notifications.get_owner_booking_confirmation_whatsapp_content(owner.name, booking_details_dict)
            notifications.send_whatsapp_message(owner.phone, owner_whatsapp_content)

        # WhatsApp to Customer (if phone is provided)
        if customer_phone:
            customer_whatsapp_content = notifications.get_customer_booking_confirmation_whatsapp_content(customer_name, owner.business_name, booking_details_dict)
            notifications.send_whatsapp_message(customer_phone, customer_whatsapp_content)

        return templates.get_template("booking_confirmation.html").render({
            "request": request,
            "owner": owner,
            "booking": db_booking,
            "customer_name": customer_name
        })
    except Exception as e:
        # Re-render booking page with error
        services = json.loads(owner.services_json) if owner.services_json else []
        availability = json.loads(owner.availability_json) if owner.availability_json else {}
        return templates.get_template("booking_page.html").render({
            "request": request,
            "owner": owner,
            "services": services,
            "availability": availability,
            "error": f"Error processing booking: {e}"
        })

@app.get("/set_locale/{locale_code}")
async def set_locale(request: Request, locale_code: str):
    request.session["locale"] = locale_code
    # Redirect back to the page the user came from
    referer = request.headers.get("referer")
    if referer:
        # Use a custom filter defined in i18n_config to update the 'lang' query param
        templates = get_templates(request)
        new_url = templates.filters['urlencode'](referer, 'lang', locale_code)
        return RedirectResponse(url=new_url, status_code=status.HTTP_302_FOUND)
    return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND) # Fallback
