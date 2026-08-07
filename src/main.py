from fastapi import FastAPI, Depends, HTTPException, status, Request, Form, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, date, time
from typing import List, Optional
import json
import calendar
from jinja2 import Environment, FileSystemLoader, select_autoescape
from . import crud, models, schemas, security, notifications
from .database import SessionLocal, engine, create_tables, get_db
from .config import settings
from gettext import gettext, translation, bindtextdomain, textdomain
import os

# --- FastAPI app setup and dependencies (inferred) ---
app = FastAPI()

# OAuth2PasswordBearer
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Jinja2 setup
_current_file_dir = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(_current_file_dir, os.pardir))
templates_dir = os.path.join(PROJECT_ROOT, 'templates')
env = Environment(
    loader=FileSystemLoader(templates_dir),
    autoescape=select_autoescape(['html', 'xml'])
)

# i18n setup
locales_dir = settings.LOCALES_DIR
bindtextdomain('messages', locales_dir)
textdomain('messages')

def _(message: str) -> str:
    return gettext(message)

env.globals['gettext'] = _
env.globals['_'] = _ # Alias for convenience

# Language middleware
@app.middleware("http")
async def add_language_middleware(request: Request, call_next):
    lang = request.cookies.get("lang", "en")
    request.state.lang = lang
    
    # Set the language for gettext
    try:
        t = translation('messages', locales_dir, languages=[lang])
        t.install()
    except Exception:
        # Fallback to default if translation fails
        translation('messages', locales_dir, languages=['en']).install()
    
    response = await call_next(request)
    return response

# Dependency to get current owner
async def get_current_owner(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
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

@app.on_event("startup")
def on_startup():
    create_tables()

# --- End FastAPI app setup and dependencies ---

@app.post("/token", response_model=schemas.Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    owner = crud.authenticate_owner(db, form_data.username, form_data.password)
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

@app.post("/owners/", response_model=schemas.Owner)
def create_owner_endpoint(owner: schemas.OwnerCreate, db: Session = Depends(get_db)):
    try:
        db_owner = crud.create_owner(db=db, owner=owner)
        return db_owner
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db), current_owner: schemas.Owner = Depends(get_current_owner)):
    bookings = crud.get_owner_bookings(db, current_owner.id)
    # Convert bookings to a list of dicts for easier Jinja2 rendering if needed
    bookings_data = [
        {
            "customer_name": booking.customer_name,
            "customer_email": booking.customer_email,
            "customer_phone": booking.customer_phone,
            "service_name": booking.service_name,
            "service_duration_minutes": booking.service_duration_minutes, # Ensure this is passed
            "booking_date": booking.booking_date.strftime("%Y-%m-%d"),
            "booking_time": booking.booking_time.strftime("%H:%M")
        } for booking in bookings
    ]

    # Parse services_json and availability_json for display
    try:
        services = json.loads(current_owner.services_json) if current_owner.services_json else []
    except json.JSONDecodeError:
        services = [] # Handle malformed JSON gracefully
    
    try:
        availability = json.loads(current_owner.availability_json) if current_owner.availability_json else {}
    except json.JSONDecodeError:
        availability = {} # Handle malformed JSON gracefully

    template = env.get_template("dashboard.html")
    return template.render(
        request=request,
        owner=current_owner,
        bookings=bookings_data,
        services=services,
        availability=availability,
        messages=[] # For displaying feedback
    )

@app.post("/dashboard/update-profile", response_class=HTMLResponse)
async def update_profile(request: Request, db: Session = Depends(get_db), current_owner: schemas.Owner = Depends(get_current_owner),
                         name: str = Form(...), business_name: str = Form(...), phone: Optional[str] = Form(None),
                         services_json: Optional[str] = Form(None), availability_json: Optional[str] = Form(None)):
    
    owner_update = schemas.OwnerProfileUpdate(
        name=name, business_name=business_name, phone=phone,
        services_json=services_json, availability_json=availability_json
    )
    messages = []
    try:
        updated_owner = crud.update_owner_profile(db, current_owner, owner_update)
        messages.append({"type": "success", "text": _("Profile updated successfully!")})
        # Refresh current_owner for the template render
        current_owner = updated_owner
    except ValueError as e:
        messages.append({"type": "error", "text": str(e)})
    except Exception as e:
        messages.append({"type": "error", "text": _("An unexpected error occurred: {error_detail}").format(error_detail=str(e))})

    # Re-fetch bookings and parse services/availability for rendering
    bookings = crud.get_owner_bookings(db, current_owner.id)
    bookings_data = [
        {
            "customer_name": booking.customer_name,
            "customer_email": booking.customer_email,
            "customer_phone": booking.customer_phone,
            "service_name": booking.service_name,
            "service_duration_minutes": booking.service_duration_minutes,
            "booking_date": booking.booking_date.strftime("%Y-%m-%d"),
            "booking_time": booking.booking_time.strftime("%H:%M")
        } for booking in bookings
    ]
    try:
        services = json.loads(current_owner.services_json) if current_owner.services_json else []
    except json.JSONDecodeError:
        services = []
    try:
        availability = json.loads(current_owner.availability_json) if current_owner.availability_json else {}
    except json.JSONDecodeError:
        availability = {}

    template = env.get_template("dashboard.html")
    return template.render(
        request=request,
        owner=current_owner,
        bookings=bookings_data,
        services=services,
        availability=availability,
        messages=messages
    )

@app.get("/book/{owner_slug}", response_class=HTMLResponse)
async def booking_page(request: Request, owner_slug: str, db: Session = Depends(get_db)):
    owner = crud.get_owner_by_slug(db, owner_slug)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Booking page not found."))

    # Parse services_json and availability_json for display
    try:
        services = json.loads(owner.services_json) if owner.services_json else []
    except json.JSONDecodeError:
        services = []
    
    try:
        availability = json.loads(owner.availability_json) if owner.availability_json else {}
    except json.JSONDecodeError:
        availability = {}

    template = env.get_template("booking_page.html")
    return template.render(
        request=request,
        owner=owner,
        services=services,
        availability=availability,
        messages=[]
    )

@app.post("/book/{owner_slug}", response_class=HTMLResponse)
async def submit_booking(request: Request, owner_slug: str, db: Session = Depends(get_db),
                         customer_name: str = Form(...), customer_email: EmailStr = Form(...),
                         customer_phone: Optional[str] = Form(None), service_name: str = Form(...),
                         booking_date_str: str = Form(...), booking_time_str: str = Form(...)):
    
    owner = crud.get_owner_by_slug(db, owner_slug)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Booking page not found."))

    messages = []
    try:
        booking_date = datetime.strptime(booking_date_str, "%Y-%m-%d").date()
        booking_time = datetime.strptime(booking_time_str, "%H:%M").time()

        booking_in = schemas.BookingCreate(
            customer_name=customer_name,
            customer_email=customer_email,
            customer_phone=customer_phone,
            service_name=service_name,
            booking_date=booking_date,
            booking_time=booking_time
        )
        
        db_booking = crud.create_booking(db=db, booking=booking_in, owner_id=owner.id)
        
        # Send notifications
        notifications.send_booking_confirmation_email(db_booking, owner)
        notifications.send_booking_notification_to_owner(db_booking, owner)
        
        # Render confirmation page
        template = env.get_template("booking_confirmation.html")
        return template.render(
            request=request,
            booking=db_booking,
            owner=owner,
            messages=[{"type": "success", "text": _("Your booking has been confirmed!")}]
        )

    except ValueError as e:
        messages.append({"type": "error", "text": str(e)})
    except Exception as e:
        messages.append({"type": "error", "text": _("An unexpected error occurred during booking: {error_detail}").format(error_detail=str(e))})

    # If error, re-render booking page with error message
    try:
        services = json.loads(owner.services_json) if owner.services_json else []
    except json.JSONDecodeError:
        services = []
    try:
        availability = json.loads(owner.availability_json) if owner.availability_json else {}
    except json.JSONDecodeError:
        availability = {}

    template = env.get_template("booking_page.html")
    return template.render(
        request=request,
        owner=owner,
        services=services,
        availability=availability,
        messages=messages,
        # Pass back form data to pre-fill if possible (optional for this task)
        customer_name=customer_name,
        customer_email=customer_email,
        customer_phone=customer_phone,
        service_name=service_name,
        booking_date_str=booking_date_str,
        booking_time_str=booking_time_str
    )

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    template = env.get_template("index.html") # Assuming an index.html exists for landing page
    return template.render(request=request)

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    template = env.get_template("login.html") # Assuming a login.html exists
    return template.render(request=request)

@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    template = env.get_template("register.html") # Assuming a register.html exists
    return template.render(request=request)

@app.post("/register", response_class=HTMLResponse)
async def register_owner(request: Request, db: Session = Depends(get_db),
                         name: str = Form(...), email: EmailStr = Form(...), password: str = Form(...),
                         business_name: str = Form(...), slug: str = Form(...), phone: Optional[str] = Form(None)):
    owner_create = schemas.OwnerCreate(name=name, email=email, password=password, business_name=business_name, slug=slug, phone=phone)
    messages = []
    try:
        crud.create_owner(db, owner_create)
        messages.append({"type": "success", "text": _("Registration successful! Please log in.")})
        template = env.get_template("login.html")
        return template.render(request=request, messages=messages)
    except ValueError as e:
        messages.append({"type": "error", "text": str(e)})
        template = env.get_template("register.html")
        return template.render(request=request, messages=messages, name=name, email=email, business_name=business_name, slug=slug, phone=phone)

# Endpoint to set language cookie
@app.get("/set-language/{lang_code}")
async def set_language(lang_code: str, response: Response):
    response.set_cookie(key="lang", value=lang_code, httponly=True, expires=datetime.now() + timedelta(days=30))
    return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
