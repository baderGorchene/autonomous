from fastapi import FastAPI, Depends, HTTPException, status, Request, Response
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from typing import List, Annotated
import json
import logging
from datetime import datetime, time, timedelta
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode
import gettext

from . import crud, models, schemas, security, notifications
from .database import engine, get_db, Base, create_tables
from .config import settings
from .i18n_config import get_jinja_env
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create tables on startup
@Base.event.listens_for(engine, "connect")
def _create_tables(dbapi_connection, connection_record):
    Base.metadata.create_all(bind=engine)

app = FastAPI()

# Add SessionMiddleware for session management (e.g., for language preference)
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

# Middleware to set language
class LanguageMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        session_locale = request.session.get("locale")
        query_locale = request.query_params.get("lang")

        if query_locale:
            request.session["locale"] = query_locale
            locale = query_locale
        elif session_locale:
            locale = session_locale
        else:
            locale = "en" # Default language

        request.state.locale = locale
        response = await call_next(request)
        return response

app.add_middleware(LanguageMiddleware)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def get_current_owner(db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = security.decode_access_token(token, credentials_exception)
        owner_id: int = payload.get("sub")
        if owner_id is None:
            raise credentials_exception
    except Exception as e:
        raise credentials_exception from e
    owner = crud.get_owner(db, owner_id=owner_id)
    if owner is None:
        raise credentials_exception
    return owner

@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.post("/token", response_model=schemas.Token)
async def login_for_access_token(form_data: Annotated[OAuth2PasswordRequestForm, Depends()], db: Session = Depends(get_db)):
    owner = crud.authenticate_owner(db, form_data.username, form_data.password)
    if not owner:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": str(owner.id)}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/signup", response_model=schemas.Owner)
async def create_owner_signup(owner: schemas.OwnerCreate, db: Session = Depends(get_db)):
    db_owner = crud.get_owner_by_email(db, email=owner.email)
    if db_owner:
        raise HTTPException(status_code=400, detail="Email already registered")
    db_owner = crud.get_owner_by_slug(db, slug=owner.slug)
    if db_owner:
        raise HTTPException(status_code=400, detail="Business URL slug already taken")
    return crud.create_owner(db=db, owner=owner)

@app.get("/owner/me", response_model=schemas.Owner)
async def read_owners_me(current_owner: Annotated[models.Owner, Depends(get_current_owner)]):
    return current_owner

@app.put("/owner/me", response_model=schemas.Owner)
async def update_owner_profile_route(
    owner_update: schemas.OwnerProfileUpdate,
    current_owner: Annotated[models.Owner, Depends(get_current_owner)],
    db: Session = Depends(get_db)
):
    # Validate services_json
    try:
        services_data = json.loads(owner_update.services_json)
        # Basic validation: ensure it's a list of dicts with 'name' and 'duration'
        if not isinstance(services_data, list) or not all(
            isinstance(s, dict) and 'name' in s and 'duration' in s for s in services_data
        ):
            raise ValueError("Invalid services format")
        current_owner.services_json = owner_update.services_json
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Services JSON is invalid")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Validate availability_json
    try:
        availability_data = json.loads(owner_update.availability_json)
        # Basic validation: ensure it's a dict with day keys and list of time ranges
        if not isinstance(availability_data, dict) or not all(
            isinstance(v, list) and all(isinstance(t, list) and len(t) == 2 for t in v)
            for v in availability_data.values()
        ):
            raise ValueError("Invalid availability format")
        current_owner.availability_json = owner_update.availability_json
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Availability JSON is invalid")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return crud.update_owner_profile(db, current_owner, owner_update)


@app.get("/owner/bookings", response_model=List[schemas.Booking])
async def get_owner_bookings_route(
    current_owner: Annotated[models.Owner, Depends(get_current_owner)],
    db: Session = Depends(get_db)
):
    bookings = crud.get_owner_bookings(db, owner_id=current_owner.id)
    return bookings

@app.get("/owner/dashboard", response_class=HTMLResponse)
async def owner_dashboard(request: Request, db: Session = Depends(get_db)):
    _ = gettext.gettext
    try:
        token = request.cookies.get("access_token")
        if not token:
            return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

        owner = get_current_owner(db=db, token=token)
        if not owner:
            return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

        # Get the Jinja2 environment with the correct locale
        env = get_jinja_env(locale=request.state.locale)
        template = env.get_template("dashboard.html")

        # Load owner data
        owner_data = schemas.Owner.from_orm(owner).dict()
        owner_data["services"] = json.loads(owner.services_json)
        owner_data["availability"] = json.loads(owner.availability_json)

        # Get bookings
        bookings = crud.get_owner_bookings(db, owner.id)
        # Format bookings for display
        formatted_bookings = []
        for booking in bookings:
            formatted_bookings.append({
                "service_name": booking.service_name,
                "customer_name": booking.customer_name,
                "customer_email": booking.customer_email,
                "customer_phone": booking.customer_phone,
                "booking_date": booking.booking_date.strftime("%Y-%m-%d"),
                "booking_time": booking.booking_time.strftime("%H:%M"),
                "notes": booking.notes,
            })

        return template.render(
            request=request,
            owner=owner_data,
            bookings=formatted_bookings,
            locale=request.state.locale
        )
    except HTTPException as e:
        if e.status_code == status.HTTP_401_UNAUTHORIZED:
            return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
        raise e
    except Exception as e:
        logger.error(f"Error rendering dashboard: {e}", exc_info=True)
        return HTMLResponse(content=f"<h1>Error loading dashboard</h1><p>{e}</p>", status_code=500)

@app.get("/{owner_slug}", response_class=HTMLResponse)
async def get_booking_page(owner_slug: str, request: Request, db: Session = Depends(get_db)):
    _ = gettext.gettext
    owner = crud.get_owner_by_slug(db, slug=owner_slug)
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")

    env = get_jinja_env(locale=request.state.locale)
    template = env.get_template("booking_page.html")

    services = json.loads(owner.services_json) if owner.services_json else []
    availability = json.loads(owner.availability_json) if owner.availability_json else {}

    # Generate available time slots for the next 7 days
    available_slots = {}
    today = datetime.now().date()
    for i in range(7):
        current_date = today + timedelta(days=i)
        day_of_week = current_date.strftime("%A").lower() # e.g., "monday"
        if day_of_week in availability:
            slots_for_day = []
            for time_range in availability[day_of_week]:
                start_time_str, end_time_str = time_range
                start_hour, start_minute = map(int, start_time_str.split(':'))
                end_hour, end_minute = map(int, end_time_str.split(':'))

                current_time_obj = time(start_hour, start_minute)
                end_time_obj = time(end_hour, end_minute)

                # Assuming services have a 'duration' in minutes
                # For simplicity, let's assume all services have a default duration for slot generation
                # In a real app, this would be tied to selected service.
                # For now, let's just generate slots based on a fixed interval (e.g., 30 min)
                # and then filter based on service duration at booking time.
                slot_duration_minutes = 30 # Default slot interval

                while current_time_obj < end_time_obj:
                    slots_for_day.append(current_time_obj.strftime("%H:%M"))
                    current_time_obj = (datetime.combine(current_date, current_time_obj) + timedelta(minutes=slot_duration_minutes)).time()
            available_slots[current_date.strftime("%Y-%m-%d")] = slots_for_day

    return template.render(
        request=request,
        owner=owner,
        services=services,
        available_slots=available_slots,
        locale=request.state.locale
    )

@app.post("/{owner_slug}/book", response_class=HTMLResponse)
async def submit_booking(owner_slug: str, request: Request, db: Session = Depends(get_db)):
    _ = gettext.gettext
    owner = crud.get_owner_by_slug(db, slug=owner_slug)
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")

    form = await request.form()
    customer_name = form.get("customer_name")
    customer_email = form.get("customer_email")
    customer_phone = form.get("customer_phone")
    service_name = form.get("service_name")
    booking_date_str = form.get("booking_date")
    booking_time_str = form.get("booking_time")
    notes = form.get("notes", "")

    try:
        booking_date = datetime.strptime(booking_date_str, "%Y-%m-%d").date()
        booking_time = datetime.strptime(booking_time_str, "%H:%M").time()
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid date or time format.")

    # Basic validation (add more comprehensive validation as needed)
    if not all([customer_name, customer_email, service_name, booking_date_str, booking_time_str]):
        raise HTTPException(status_code=400, detail="Missing required booking information.")

    booking_data = schemas.BookingCreate(
        customer_name=customer_name,
        customer_email=customer_email,
        customer_phone=customer_phone,
        service_name=service_name,
        booking_date=booking_date,
        booking_time=booking_time,
        notes=notes
    )

    try:
        db_booking = crud.create_booking(db=db, booking=booking_data, owner_id=owner.id)

        # Send notifications
        notifications.send_owner_notification(owner, db_booking, settings.SENDGRID_API_KEY, settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN, settings.TWILIO_WHATSAPP_NUMBER)
        notifications.send_customer_confirmation(owner, db_booking, settings.SENDGRID_API_KEY)

        env = get_jinja_env(locale=request.state.locale)
        template = env.get_template("booking_confirmation.html")
        return template.render(request=request, booking=db_booking, owner=owner, locale=request.state.locale)

    except Exception as e:
        logger.error(f"Error creating booking or sending notification: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Booking failed: {e}")

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    env = get_jinja_env(locale=request.state.locale)
    template = env.get_template("login.html")
    return template.render(request=request, locale=request.state.locale)

@app.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request):
    env = get_jinja_env(locale=request.state.locale)
    template = env.get_template("signup.html")
    return template.render(request=request, locale=request.state.locale)
