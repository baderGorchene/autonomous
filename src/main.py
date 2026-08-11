from fastapi import FastAPI, Depends, HTTPException, status, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import date, timedelta
import logging

# Security related imports
from . import security, schemas, models, database, notifications, analytics, availability_utils
from .config import settings
from .dependencies import get_db, get_current_owner, get_current_customer, get_current_admin_user, get_language_code
from .i18n import gettext as _ # Assuming gettext is initialized
from fastapi_limiter import FastAPILimiter
from fastapi_limiter.depends import RateLimiter
import redis.asyncio as redis
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import PlainTextResponse

# --- Security Headers Middleware ---
# A simple middleware to add security headers.
# More robust solutions might use a library or more granular control.
class SecureHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains; preload'
        response.headers['Referrer-Policy'] = 'no-referrer-when-downgrade'
        # Content-Security-Policy is complex and needs careful tuning.
        # For an MVP, a basic one might be:
        # response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self';"
        return response

app = FastAPI(
    title="BookSlot API",
    description="Booking page for local service businesses",
    version="0.1.0"
)

# --- CORS Middleware ---
# Configure CORS to allow specific origins in production
origins = [
    settings.APP_BASE_URL, # Allow requests from the application's base URL
    "http://localhost:3000", # For local frontend development
    "http://localhost:8000"
]
if settings.APP_BASE_URL.startswith("https"):
    origins.append(settings.APP_BASE_URL.replace("https", "http")) # For local testing with http

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins, # TODO: Set this to `origins` in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Security Headers Middleware ---
app.add_middleware(SecureHeadersMiddleware)

# --- Rate Limiting Initialization ---
@app.on_event("startup")
async def startup():
    redis_connection = redis.from_url(settings.REDIS_URL, encoding="utf8", decode_responses=True)
    await FastAPILimiter.init(redis_connection)
    logging.info("FastAPILimiter initialized.")

@app.on_event("shutdown")
async def shutdown():
    await FastAPILimiter.close()
    logging.info("FastAPILimiter closed.")


# Templates setup (assuming Jinja2)
templates = Jinja2Templates(directory="templates")

# --- Health Check Endpoint ---
@app.get("/health", response_class=PlainTextResponse, tags=["Monitoring"])
async def health_check():
    return "OK"

# --- Authentication Endpoints ---

@app.post("/owner/signup", response_model=schemas.OwnerOut, tags=["Owner Authentication"])
async def owner_signup(owner: schemas.OwnerCreate, db: Session = Depends(get_db),
                       # Rate limit signup attempts from a single IP
                       rate_limiter: RateLimiter = Depends(RateLimiter(times=5, seconds=30))):
    db_owner = db.query(models.Owner).filter(models.Owner.email == owner.email).first()
    if db_owner:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_("Email already registered"))
    hashed_password = security.get_password_hash(owner.password)
    db_owner = models.Owner(
        email=owner.email,
        hashed_password=hashed_password,
        name=owner.name,
        phone=owner.phone,
        is_admin=False
    )
    db.add(db_owner)
    db.commit()
    db.refresh(db_owner)
    return db_owner

@app.post("/owner/token", response_model=schemas.Token, tags=["Owner Authentication"])
async def owner_login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db),
                                     # Rate limit login attempts from a single IP
                                     rate_limiter: RateLimiter = Depends(RateLimiter(times=5, seconds=30))):
    owner = security.authenticate_owner(db, form_data.username, form_data.password)
    if not owner:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_("Incorrect email or password"),
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": owner.email, "role": "owner"}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

# Placeholder for customer authentication
@app.post("/customer/signup", response_model=schemas.CustomerOut, tags=["Customer Authentication"])
async def customer_signup(customer: schemas.CustomerCreate, db: Session = Depends(get_db),
                          rate_limiter: RateLimiter = Depends(RateLimiter(times=5, seconds=30))):
    db_customer = db.query(models.Customer).filter(models.Customer.email == customer.email).first()
    if db_customer:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_("Email already registered"))
    hashed_password = security.get_password_hash(customer.password)
    db_customer = models.Customer(
        email=customer.email,
        hashed_password=hashed_password,
        name=customer.name,
        phone=customer.phone
    )
    db.add(db_customer)
    db.commit()
    db.refresh(db_customer)
    return db_customer

@app.post("/customer/token", response_model=schemas.Token, tags=["Customer Authentication"])
async def customer_login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db),
                                        rate_limiter: RateLimiter = Depends(RateLimiter(times=5, seconds=30))):
    customer = security.authenticate_customer(db, form_data.username, form_data.password)
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_("Incorrect email or password"),
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": customer.email, "role": "customer"}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

# --- Owner Dashboard Endpoints ---
@app.get("/owner/dashboard", response_class=HTMLResponse, tags=["Owner Dashboard"])
async def owner_dashboard(request: Request, current_owner: models.Owner = Depends(get_current_owner), db: Session = Depends(get_db)):
    lang_code = get_language_code(request)
    _ = security.gettext_lazy(lang_code)
    # ... (existing dashboard logic)
    upcoming_bookings = db.query(models.Booking).filter(
        models.Booking.owner_id == current_owner.id,
        models.Booking.date >= date.today()
    ).order_by(models.Booking.date, models.Booking.time).all()

    monthly_bookings_data = analytics.get_monthly_bookings_data(db, current_owner.id)
    popular_services_data = analytics.get_popular_services_data(db, current_owner.id)

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "owner": current_owner,
            "upcoming_bookings": upcoming_bookings,
            "monthly_bookings_data": monthly_bookings_data,
            "popular_services_data": popular_services_data,
            "gettext": _
        }
    )

# Placeholder for other owner, customer, admin, public endpoints
# ... (e.g., /owner/services, /owner/profile, /book/{owner_name}, /admin/owners)
# All these endpoints should implement proper authorization checks.
# For example, an endpoint to update a service:
@app.put("/owner/services/{service_id}", response_model=schemas.ServiceOut, tags=["Owner Services"])
async def update_owner_service(
    service_id: int,
    service_update: schemas.ServiceUpdate,
    current_owner: models.Owner = Depends(get_current_owner),
    db: Session = Depends(get_db)
):
    db_service = db.query(models.Service).filter(
        models.Service.id == service_id,
        models.Service.owner_id == current_owner.id # Crucial object-level authorization
    ).first()
    if not db_service:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Service not found or not owned by you"))

    for key, value in service_update.dict(exclude_unset=True).items():
        setattr(db_service, key, value)
    db.commit()
    db.refresh(db_service)
    return db_service


# --- Public Booking Page ---
@app.get("/book/{owner_name}", response_class=HTMLResponse, tags=["Public Booking"])
async def get_booking_page(request: Request, owner_name: str, db: Session = Depends(get_db)):
    lang_code = get_language_code(request)
    _ = security.gettext_lazy(lang_code)

    owner = db.query(models.Owner).filter(models.Owner.name == owner_name).first()
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Owner not found"))

    services = db.query(models.Service).filter(models.Service.owner_id == owner.id).all()
    # ... (rest of the booking page logic)

    return templates.TemplateResponse(
        "booking_page.html",
        {"request": request, "owner": owner, "services": services, "gettext": _}
    )

@app.post("/book/{owner_name}/submit", response_model=schemas.BookingOut, tags=["Public Booking"])
async def submit_booking(
    owner_name: str,
    booking_in: schemas.BookingCreate,
    db: Session = Depends(get_db),
    # Rate limit booking submissions to prevent spam/abuse
    rate_limiter: RateLimiter = Depends(RateLimiter(times=10, seconds=60))
):
    # ... (booking submission logic, including availability checks, email notifications)
    owner = db.query(models.Owner).filter(models.Owner.name == owner_name).first()
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Owner not found"))

    service = db.query(models.Service).filter(
        models.Service.id == booking_in.service_id,
        models.Service.owner_id == owner.id
    ).first()
    if not service:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Service not found for this owner"))

    # Validate availability
    available_slots = availability_utils.get_available_slots_for_day(
        db, owner.id, service.id, booking_in.date, service.duration_minutes
    )
    if booking_in.time not in available_slots:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_("Selected slot is not available"))

    # Create the booking
    db_booking = models.Booking(
        owner_id=owner.id,
        service_id=service.id,
        customer_name=booking_in.customer_name,
        customer_email=booking_in.customer_email,
        customer_phone=booking_in.customer_phone,
        date=booking_in.date,
        time=booking_in.time,
        notes=booking_in.notes,
        is_recurring=booking_in.is_recurring,
        recurrence_id=booking_in.recurrence_id,
        recurrence_pattern=booking_in.recurrence_pattern
    )
    db.add(db_booking)
    db.commit()
    db.refresh(db_booking)

    # Send notifications
    notifications.send_booking_confirmation_email_to_customer(
        customer_email=booking_in.customer_email,
        owner_name=owner.name,
        service_name=service.name,
        booking_date=booking_in.date,
        booking_time=booking_in.time,
        lang_code=lang_code
    )
    notifications.send_booking_notification_to_owner(
        owner_email=owner.email,
        owner_phone=owner.phone,
        customer_name=booking_in.customer_name,
        service_name=service.name,
        booking_date=booking_in.date,
        booking_time=booking_in.time,
        lang_code=lang_code
    )

    return db_booking

# Placeholder for review endpoints
# @app.post("/reviews/{owner_id}", response_model=schemas.ReviewOut, tags=["Reviews"])
# async def submit_review(...): pass

# Placeholder for Stripe webhook
# @app.post("/stripe-webhook", tags=["Payments"])
# async def stripe_webhook(request: Request, db: Session = Depends(get_db)): pass

# Placeholder for admin panel
# @app.get("/admin/dashboard", response_class=HTMLResponse, tags=["Admin"])
# async def admin_dashboard(...): pass
