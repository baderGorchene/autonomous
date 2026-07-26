from fastapi import FastAPI, Depends, HTTPException, status, Request, Form, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from typing import Annotated, Dict
from datetime import datetime, timedelta
import json
import os
import logging

from . import crud, models, schemas, security, notifications
from .database import SessionLocal, engine
from .config import settings
from .i18n_config import get_jinja_env

logging.basicConfig(level=logging.INFO)

# Ensure all models are created in the database
models.Base.metadata.create_all(bind=engine)

app = FastAPI()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Dependency to get current owner
async def get_current_owner(token: Annotated[str, Depends(oauth2_scheme)], db: Annotated[Session, Depends(get_db)]):
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
    except Exception:
        raise credentials_exception
    owner = crud.get_owner(db, owner_id=owner_id)
    if owner is None:
        raise credentials_exception
    return owner

# Jinja2 setup
templates = get_jinja_env()

# Middleware for i18n and session/flash messages (simplified)
@app.middleware("http")
async def add_i18n_middleware(request: Request, call_next):
    # Determine locale from query param, cookie, or default
    locale = request.query_params.get("lang") or request.cookies.get("lang") or "en"
    request.state.locale = locale
    request.state.gettext = get_jinja_env(locale).gettext
    response = await call_next(request)
    # Set cookie if locale changed
    if request.cookies.get("lang") != locale:
        response.set_cookie(key="lang", value=locale, httponly=True)
    return response

# Routes
@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.get_template("home.html").render({"request": request})

@app.get("/signup", response_class=HTMLResponse)
async def signup_form(request: Request):
    return templates.get_template("signup.html").render({"request": request})

@app.post("/signup", response_class=HTMLResponse)
async def signup_owner(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    name: Annotated[str, Form()],
    email: Annotated[str, Form()],
    password: Annotated[str, Form()],
    business_name: Annotated[str, Form()],
    slug: Annotated[str, Form()]
):
    db_owner = crud.get_owner_by_email(db, email=email)
    if db_owner:
        raise HTTPException(status_code=400, detail="Email already registered")
    db_owner = crud.get_owner_by_slug(db, slug=slug)
    if db_owner:
        raise HTTPException(status_code=400, detail="Slug already taken")
    
    owner_in = schemas.OwnerCreate(name=name, email=email, password=password, business_name=business_name, slug=slug)
    owner = crud.create_owner(db=db, owner=owner_in)
    
    # After successful signup, log them in or redirect to login
    response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    return response

@app.get("/login", response_class=HTMLResponse)
async def login_form(request: Request):
    return templates.get_template("login.html").render({"request": request})

@app.post("/token")
async def login_for_access_token(
    response: Response, form_data: Annotated[OAuth2PasswordRequestForm, Depends()], db: Annotated[Session, Depends(get_db)]
):
    owner = crud.authenticate_owner(db, form_data.username, form_data.password)
    if not owner:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": str(owner.id)}, expires_delta=access_token_expires
    )
    # Set token in cookie for browser-based auth
    response.set_cookie(key="access_token", value=access_token, httponly=True)
    return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, current_owner: Annotated[models.Owner, Depends(get_current_owner)], db: Annotated[Session, Depends(get_db)]):
    upcoming_bookings = db.query(models.Booking).filter(
        models.Booking.owner_id == current_owner.id,
        models.Booking.booking_time >= datetime.now()
    ).order_by(models.Booking.booking_time).all()
    
    services = json.loads(current_owner.services_json) if current_owner.services_json else []
    availability = json.loads(current_owner.availability_json) if current_owner.availability_json else {}

    return templates.get_template("dashboard.html").render(
        {"request": request, "owner": current_owner, "upcoming_bookings": upcoming_bookings, "services": services, "availability": availability}
    )

@app.post("/dashboard/profile", response_class=HTMLResponse)
async def update_profile(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_owner: Annotated[models.Owner, Depends(get_current_owner)],
    name: Annotated[str, Form()],
    business_name: Annotated[str, Form()],
    phone: Annotated[str, Form()],
    services_json: Annotated[str, Form()],
    availability_json: Annotated[str, Form()]
):
    # Validate JSON inputs
    try:
        parsed_services = json.loads(services_json)
        parsed_availability = json.loads(availability_json)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON for services or availability")

    owner_update = schemas.OwnerProfileUpdate(name=name, business_name=business_name, phone=phone)
    updated_owner = crud.update_owner_profile(db, current_owner, owner_update)
    
    # Update JSON fields directly after validation
    updated_owner.services_json = services_json
    updated_owner.availability_json = availability_json
    db.add(updated_owner)
    db.commit()
    db.refresh(updated_owner)
    
    return RedirectResponse(url="/dashboard?message=Profile updated successfully", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/{owner_slug}", response_class=HTMLResponse)
async def booking_page(request: Request, owner_slug: str, db: Annotated[Session, Depends(get_db)]):
    owner = crud.get_owner_by_slug(db, slug=owner_slug)
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")
    
    services = json.loads(owner.services_json) if owner.services_json else []
    availability = json.loads(owner.availability_json) if owner.availability_json else {}

    return templates.get_template("booking_page.html").render(
        {"request": request, "owner": owner, "services": services, "availability": availability}
    )

@app.post("/{owner_slug}/book", response_class=HTMLResponse)
async def submit_booking(
    request: Request,
    owner_slug: str,
    db: Annotated[Session, Depends(get_db)],
    customer_name: Annotated[str, Form()],
    customer_email: Annotated[str, Form()],
    customer_phone: Annotated[str, Form()],
    service_id: Annotated[int, Form()],
    booking_time_str: Annotated[str, Form()]
):
    owner = crud.get_owner_by_slug(db, slug=owner_slug)
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")
    
    try:
        booking_time = datetime.strptime(booking_time_str, "%Y-%m-%d %H:%M")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid booking time format")

    # Basic check for availability (more complex logic needed for real app)
    # For MVP, just check if it's in the future and owner has some availability set.
    if booking_time < datetime.now():
        raise HTTPException(status_code=400, detail="Cannot book in the past")
    
    # Get service details
    services = json.loads(owner.services_json)
    selected_service = next((s for s in services if s.get("id") == service_id), None)
    if not selected_service:
        raise HTTPException(status_code=400, detail="Invalid service selected")

    booking_in = schemas.BookingCreate(
        customer_name=customer_name,
        customer_email=customer_email,
        customer_phone=customer_phone,
        service_name=selected_service.get("name"),
        booking_time=booking_time,
        service_duration_minutes=selected_service.get("duration", 30) # Default duration
    )
    
    try:
        db_booking = crud.create_booking(db=db, booking=booking_in, owner_id=owner.id)
        
        # Send notifications
        notifications.send_booking_confirmation_email(
            customer_email, customer_name, selected_service.get("name"), booking_time, owner.name, owner.business_name
        )
        notifications.send_owner_notification(
            owner.email, owner.phone, customer_name, customer_email, customer_phone, selected_service.get("name"), booking_time
        )
        
        return templates.get_template("booking_confirmation.html").render(
            {"request": request, "booking": db_booking, "owner": owner}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Booking failed: {e}")
