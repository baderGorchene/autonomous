from fastapi import FastAPI, Depends, HTTPException, status, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta, datetime
import json
import os
import gettext

from . import models, schemas, crud, security, database, notifications
from .config import settings
from .i18n_config import get_jinja_env, LOCALES_DIR

# Initialize FastAPI app
app = FastAPI()

# Create database tables
models.Base.metadata.create_all(bind=database.engine)

# OAuth2PasswordBearer for token authentication
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Dependency to get DB session
def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Helper for i18n
def get_locale(request: Request):
    # Get locale from query parameter, cookie, or default to 'en'
    locale = request.query_params.get('lang', request.cookies.get('lang', 'en'))
    if locale not in ['en', 'ar', 'fr']: # Supported languages
        locale = 'en'
    return locale

@app.middleware("http")
async def add_language_cookie(request: Request, call_next):
    lang = request.query_params.get('lang')
    response = await call_next(request)
    if lang:
        response.set_cookie(key="lang", value=lang, httponly=False, max_age=3600*24*30) # 30 days
    return response

# Get Jinja2 environment
def get_templates(request: Request):
    locale = get_locale(request)
    return get_jinja_env(locale)

# Dependency for current owner
async def get_current_owner(request: Request, db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = security.decode_access_token(token)
        owner_id: int = payload.get("sub")
        if owner_id is None:
            raise credentials_exception
        token_data = schemas.TokenData(id=owner_id)
    except Exception:
        raise credentials_exception
    owner = crud.get_owner(db, owner_id=token_data.id)
    if owner is None:
        raise credentials_exception
    return owner

# --- Authentication Routes ---
@app.post("/token", response_model=schemas.Token)
async def login_for_access_token(db: Session = Depends(get_db), form_data: OAuth2PasswordRequestForm = Depends()):
    owner = crud.authenticate_owner(db, form_data.username, form_data.password)
    if not owner:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": owner.id}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/signup", response_model=schemas.Owner)
def create_owner_signup(owner: schemas.OwnerCreate, db: Session = Depends(get_db)):
    db_owner = crud.get_owner_by_email(db, email=owner.email)
    if db_owner:
        raise HTTPException(status_code=400, detail="Email already registered")
    db_owner = crud.get_owner_by_slug(db, slug=owner.slug)
    if db_owner:
        raise HTTPException(status_code=400, detail="Slug already taken")
    return crud.create_owner(db=db, owner=owner)

# --- Owner Dashboard Routes ---
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request, db: Session = Depends(get_db), current_owner: models.Owner = Depends(get_current_owner)):
    _ = get_templates(request).gettext
    # Fetch upcoming bookings for the current owner
    upcoming_bookings = db.query(models.Booking).filter(
        models.Booking.owner_id == current_owner.id,
        models.Booking.booking_date >= datetime.now().date()
    ).order_by(models.Booking.booking_date, models.Booking.booking_time).all()

    # Parse services and availability
    services = json.loads(current_owner.services_json) if current_owner.services_json else []
    availability = json.loads(current_owner.availability_json) if current_owner.availability_json else {}

    return get_templates(request).get_template("dashboard.html").render(
        request=request,
        owner=current_owner,
        upcoming_bookings=upcoming_bookings,
        services=services,
        availability=availability,
        _(key="Dashboard") # Example translation call
    )

@app.post("/dashboard/profile", response_class=HTMLResponse)
async def update_profile(
    request: Request,
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(get_current_owner),
    name: str = Form(...),
    business_name: str = Form(...),
    phone: str = Form(...),
    services_json: str = Form(...),
    availability_json: str = Form(...),
):
    _ = get_templates(request).gettext
    try:
        # Validate JSON inputs
        validated_services = json.loads(services_json)
        validated_availability = json.loads(availability_json)

        # Update owner profile
        owner_update = schemas.OwnerProfileUpdate(
            name=name,
            business_name=business_name,
            phone=phone
        )
        updated_owner = crud.update_owner_profile(db, current_owner, owner_update)
        updated_owner.services_json = json.dumps(validated_services)
        updated_owner.availability_json = json.dumps(validated_availability)
        db.add(updated_owner)
        db.commit()
        db.refresh(updated_owner)

        return RedirectResponse(url=app.url_path_for("dashboard_page"), status_code=status.HTTP_303_SEE_OTHER)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON format for services or availability.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")

# --- Public Booking Page Routes ---
@app.get("/{owner_slug}", response_class=HTMLResponse)
async def booking_page(request: Request, owner_slug: str, db: Session = Depends(get_db)):
    _ = get_templates(request).gettext
    owner = crud.get_owner_by_slug(db, slug=owner_slug)
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")

    services = json.loads(owner.services_json) if owner.services_json else []
    availability = json.loads(owner.availability_json) if owner.availability_json else {}

    return get_templates(request).get_template("booking_page.html").render(
        request=request,
        owner=owner,
        services=services,
        availability=availability,
        _(key="BookSlot") # Example translation call
    )

@app.post("/{owner_slug}/book", response_class=HTMLResponse)
async def submit_booking(
    request: Request,
    owner_slug: str,
    db: Session = Depends(get_db),
    customer_name: str = Form(...),
    customer_email: str = Form(...),
    customer_phone: str = Form(...),
    service_id: int = Form(...),
    booking_date: str = Form(...),
    booking_time: str = Form(...),
):
    _ = get_templates(request).gettext
    owner = crud.get_owner_by_slug(db, slug=owner_slug)
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")

    # Basic validation (more robust validation needed for production)
    try:
        parsed_date = datetime.strptime(booking_date, "%Y-%m-%d").date()
        # You might want to combine date and time to check against availability
        # For simplicity, we'll just store them as strings for now based on schema
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format.")

    # Find the selected service
    services = json.loads(owner.services_json) if owner.services_json else []
    selected_service = next((s for s in services if s.get("id") == service_id), None)
    if not selected_service:
        raise HTTPException(status_code=400, detail="Invalid service selected.")

    booking_data = schemas.BookingCreate(
        customer_name=customer_name,
        customer_email=customer_email,
        customer_phone=customer_phone,
        service_name=selected_service["name"],
        booking_date=parsed_date,
        booking_time=booking_time,
        status="pending" # Default status
    )

    try:
        db_booking = crud.create_booking(db=db, booking=booking_data, owner_id=owner.id)

        # Send notifications
        notifications.send_booking_confirmation_email(
            owner_email=owner.email,
            customer_email=customer_email,
            owner_name=owner.name,
            customer_name=customer_name,
            service_name=selected_service["name"],
            booking_date=booking_date,
            booking_time=booking_time,
            customer_phone=customer_phone,
            locale=get_locale(request)
        )
        notifications.send_whatsapp_notification(
            owner_phone=owner.phone,
            customer_name=customer_name,
            service_name=selected_service["name"],
            booking_date=booking_date,
            booking_time=booking_time,
            locale=get_locale(request)
        )

        return get_templates(request).get_template("booking_confirmation.html").render(
            request=request,
            booking=db_booking,
            owner=owner,
            _(key="Booking Confirmed")
        )
    except Exception as e:
        # Log the error for debugging
        print(f"Booking submission failed: {e}")
        raise HTTPException(status_code=500, detail=_("An error occurred during booking. Please try again later."))

# --- Health Check ---
@app.get("/health")
def health_check():
    return {"status": "ok"}