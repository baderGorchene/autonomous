from fastapi import FastAPI, Depends, HTTPException, status, Request, Response, Form, File, UploadFile
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload
from datetime import datetime, date, timedelta, time
from typing import List, Dict, Any, Optional
import json
import stripe
import os
import gettext
import babel.dates
from babel import Locale
import pytz # For timezone handling if needed, though not explicitly in previous steps

# NEW IMPORTS FOR CACHING
from fastapi_cache import FastAPICache
from fastapi_cache.backends.redis import RedisBackend
from fastapi_cache.decorator import cache
from redis import asyncio as aioredis
from redis.asyncio.connection import ConnectionPool

# Existing imports
from . import models, schemas, security, notifications, analytics, availability_utils
from .database import SessionLocal, engine, get_db
from .config import settings

# --- Initialize FastAPI App ---
app = FastAPI()

# --- Stripe Configuration ---
stripe.api_key = settings.STRIPE_API_KEY

# --- Jinja2 Templates Configuration ---
templates = Jinja2Templates(directory="templates")

# --- i18n (Internationalization) Setup ---
# This part assumes a directory structure like:
# locales/
#   ar/LC_MESSAGES/messages.mo
#   fr/LC_MESSAGES/messages.mo
LANGUAGES = {"en": "English", "ar": "العربية", "fr": "Français"}
DEFAULT_LANGUAGE = "en"

# Function to get translation
def get_translator(lang_code: str):
    try:
        localedir = os.path.join(os.path.dirname(__file__), '..', 'locales')
        t = gettext.translation('messages', localedir, languages=[lang_code], fallback=True)
        return t.gettext
    except Exception:
        return gettext.gettext # Fallback to default

@app.middleware("http")
async def i18n_middleware(request: Request, call_next):
    lang_code = request.cookies.get("lang", DEFAULT_LANGUAGE)
    if lang_code not in LANGUAGES:
        lang_code = DEFAULT_LANGUAGE
    
    request.state.lang = lang_code
    request.state.gettext = get_translator(lang_code)
    
    request.state.template_globals = {
        "_": request.state.gettext,
        "lang": request.state.lang,
        "LANGUAGES": LANGUAGES
    }
    
    response = await call_next(request)
    return response

# --- Cache Statistics ---
cache_stats = {"hits": 0, "misses": 0}

@app.middleware("http")
async def track_cache_stats_middleware(request: Request, call_next):
    """Middleware to track cache hit/miss ratios."""
    response = await call_next(request)
    cache_header = response.headers.get("X-FastAPI-Cache")
    if cache_header == "HIT":
        cache_stats["hits"] += 1
    elif cache_header == "MISS":
        cache_stats["misses"] += 1
    return response


@app.on_event("startup")
async def startup_event():
    # Database setup
    models.Base.metadata.create_all(bind=engine)

    # Redis connection pooling for FastAPI-Cache
    pool = ConnectionPool.from_url(
        settings.REDIS_URL,
        max_connections=10,
        decode_responses=False, # MUST be False
    )
    redis_client = aioredis.Redis(connection_pool=pool)
    FastAPICache.init(RedisBackend(redis_client), prefix="fastapi-cache")
    print("FastAPI Cache initialized with Redis backend.")

    # Jinja2 filters setup
    def format_currency(value, currency='USD', locale='en_US'):
        try:
            if locale.startswith('ar'):
                locale = 'ar_AE' # Example, adjust as needed
            return babel.numbers.format_currency(value, currency, locale=locale)
        except Exception:
            return f"{value} {currency}" # Fallback
    templates.env.filters["currency"] = format_currency

# --- Health Check ---
@app.get("/health", response_model=Dict[str, str], tags=["Health"])
async def health_check():
    return {"status": "ok"}

# --- Language Toggle Endpoint ---
@app.post("/toggle-language", response_class=RedirectResponse, tags=["i18n"])
async def toggle_language(request: Request, lang: str = Form(...)):
    response = RedirectResponse(request.headers.get("referer", "/"), status_code=status.HTTP_302_FOUND)
    response.set_cookie(key="lang", value=lang, httponly=True, max_age=365 * 24 * 60 * 60)
    return response

# --- Owner Authentication and Management ---
@app.post("/owner/register", response_model=schemas.Owner, tags=["Owner Auth"])
async def register_owner(owner: schemas.OwnerCreate, db: Session = Depends(get_db)):
    db_owner = db.query(models.Owner).filter(models.Owner.email == owner.email).first()
    if db_owner:
        raise HTTPException(status_code=400, detail="Email already registered")
    hashed_password = security.get_password_hash(owner.password)
    db_owner = models.Owner(
        email=owner.email,
        hashed_password=hashed_password,
        name=owner.name,
        phone=owner.phone,
        username=owner.username
    )
    db.add(db_owner)
    db.commit()
    db.refresh(db_owner)
    return db_owner

@app.post("/owner/token", response_model=schemas.Token, tags=["Owner Auth"])
async def login_for_access_token(
    request: Request,
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    owner = security.authenticate_owner(db, form_data.username, form_data.password)
    if not owner:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=request.state.gettext("Incorrect email or password"),
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": owner.email, "user_type": "owner"}, expires_delta=access_token_expires
    )
    # Set access token in an HttpOnly cookie
    response.set_cookie(
        key="access_token",
        value=f"Bearer {access_token}",
        httponly=True,
        max_age=access_token_expires.total_seconds(),
        samesite="Lax", # Or "Strict" depending on security needs
        secure=True # Use True in production with HTTPS
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/owner/me", response_model=schemas.Owner, tags=["Owner Auth"])
async def read_owners_me(current_owner: schemas.Owner = Depends(security.get_current_active_owner)):
    return current_owner

@app.post("/owner/logout", response_class=RedirectResponse, tags=["Owner Auth"])
async def owner_logout(response: Response):
    response.delete_cookie("access_token")
    return RedirectResponse("/owner/login", status_code=status.HTTP_302_FOUND)

@app.put("/owner/profile", response_model=schemas.Owner, tags=["Owner Management"])
async def update_owner_profile(
    owner_update: schemas.OwnerUpdate,
    current_owner: models.Owner = Depends(security.get_current_active_owner),
    db: Session = Depends(get_db)
):
    try:
        for field, value in owner_update.dict(exclude_unset=True).items():
            setattr(current_owner, field, value)
        db.add(current_owner)
        db.commit()
        db.refresh(current_owner)
        return current_owner
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error updating profile: {e}")

# --- Service Management ---
@app.post("/owner/services", response_model=schemas.Service, tags=["Service Management"])
async def create_service(
    service: schemas.ServiceCreate,
    current_owner: models.Owner = Depends(security.get_current_active_owner),
    db: Session = Depends(get_db)
):
    db_service = models.Service(**service.dict(), owner_id=current_owner.id)
    db.add(db_service)
    db.commit()
    db.refresh(db_service)
    return db_service

@app.get("/owner/services", response_model=List[schemas.Service], tags=["Service Management"])
async def get_owner_services(
    current_owner: models.Owner = Depends(security.get_current_active_owner),
    db: Session = Depends(get_db)
):
    return db.query(models.Service).filter(models.Service.owner_id == current_owner.id).all()

# --- Availability Management ---
@app.post("/owner/availability", response_model=schemas.Availability, tags=["Availability Management"])
async def create_availability(
    availability: schemas.AvailabilityCreate,
    current_owner: models.Owner = Depends(security.get_current_active_owner),
    db: Session = Depends(get_db)
):
    db_availability = models.Availability(**availability.dict(), owner_id=current_owner.id)
    db.add(db_availability)
    db.commit()
    db.refresh(db_availability)
    return db_availability

@app.get("/owner/availability", response_model=List[schemas.Availability], tags=["Availability Management"])
async def get_owner_availability(
    current_owner: models.Owner = Depends(security.get_current_active_owner),
    db: Session = Depends(get_db)
):
    return db.query(models.Availability).filter(models.Availability.owner_id == current_owner.id).all()

# --- Public Booking Page ---
@app.get("/book/{owner_username}", response_class=HTMLResponse, tags=["Booking"])
@cache(expire=60 * 5) # Cache for 5 minutes
async def get_booking_page_data(owner_username: str, request: Request, db: Session = Depends(get_db)):
    _ = request.state.gettext
    owner = db.query(models.Owner).filter(models.Owner.username == owner_username).first()
    if not owner:
        raise HTTPException(status_code=404, detail=_("Owner not found"))

    services = db.query(models.Service).filter(models.Service.owner_id == owner.id).all()
    
    # Fetch reviews for the owner
    reviews = db.query(models.Review).filter(models.Review.owner_id == owner.id).all()

    return templates.TemplateResponse(
        "booking_page.html",
        {
            "request": request,
            "owner": owner,
            "services": services,
            "reviews": reviews,
            "lang": request.state.lang,
            "LANGUAGES": LANGUAGES,
            "_": _ # Pass gettext function to template
        }
    )

@app.get("/api/slots/{owner_id}/{service_id}/{date_str}", response_model=List[str], tags=["Booking"])
@cache(expire=60 * 2) # Cache for 2 minutes, as availability can change more frequently
async def get_available_slots(
    owner_id: int,
    service_id: int,
    date_str: str,
    db: Session = Depends(get_db)
):
    try:
        target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")
    
    service = db.query(models.Service).filter(models.Service.id == service_id, models.Service.owner_id == owner_id).first()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found for this owner.")

    slots = availability_utils.get_available_slots_for_day(
        db, owner_id, service_id, target_date, service.duration_minutes
    )
    return [s.strftime("%H:%M") for s in slots]

@app.post("/book/{owner_username}/submit", response_class=HTMLResponse, tags=["Booking"])
async def submit_booking(
    owner_username: str,
    request: Request,
    customer_name: str = Form(...),
    customer_email: str = Form(...),
    customer_phone: Optional[str] = Form(None),
    service_id: int = Form(...),
    booking_date: date = Form(..., alias="date"),
    booking_time: str = Form(..., alias="time"), # Expect "HH:MM"
    recurrence_type: Optional[models.RecurrenceType] = Form(None),
    recurrence_value: Optional[str] = Form(None),
    recurrence_end_date: Optional[date] = Form(None),
    db: Session = Depends(get_db)
):
    _ = request.state.gettext
    owner = db.query(models.Owner).filter(models.Owner.username == owner_username).first()
    if not owner:
        raise HTTPException(status_code=404, detail=_("Owner not found"))

    service = db.query(models.Service).filter(models.Service.id == service_id, models.Service.owner_id == owner.id).first()
    if not service:
        raise HTTPException(status_code=404, detail=_("Service not found"))
    
    # Convert booking_time string to time object
    try:
        parsed_booking_time = datetime.strptime(booking_time, "%H:%M").time()
    except ValueError:
        raise HTTPException(status_code=400, detail=_("Invalid time format. Use HH:MM."))

    # Validate slot availability (re-check to prevent double bookings)
    available_slots = availability_utils.get_available_slots_for_day(
        db, owner.id, service.id, booking_date, service.duration_minutes
    )
    if parsed_booking_time not in available_slots:
        raise HTTPException(status_code=400, detail=_("Selected slot is no longer available."))

    # Handle recurring bookings
    if recurrence_type:
        # Create initial booking
        db_booking = models.Booking(
            owner_id=owner.id,
            service_id=service.id,
            customer_name=customer_name,
            customer_email=customer_email,
            customer_phone=customer_phone,
            date=booking_date,
            time=parsed_booking_time,
            is_recurring=True,
            recurrence_type=recurrence_type,
            recurrence_value=recurrence_value,
            recurrence_end_date=recurrence_end_date
        )
        db.add(db_booking)
        db.commit()
        db.refresh(db_booking)

        # Logic to generate and save future recurring bookings (simplified for brevity)
        # This would typically involve a loop based on recurrence_type and recurrence_value
        # For an MVP, we might only create the first one and rely on a background job
        # to generate future ones, or create a few upfront.
        # For now, let's just create the initial one.
        # notifications.send_recurring_booking_confirmation(owner, db_booking, service)
        # notifications.send_recurring_booking_confirmation_to_customer(db_booking, service, owner)

    else:
        db_booking = models.Booking(
            owner_id=owner.id,
            service_id=service.id,
            customer_name=customer_name,
            customer_email=customer_email,
            customer_phone=customer_phone,
            date=booking_date,
            time=parsed_booking_time,
            is_recurring=False
        )
        db.add(db_booking)
        db.commit()
        db.refresh(db_booking)

    # Send notifications
    try:
        notifications.send_booking_confirmation_to_owner(owner, db_booking, service, request.state.lang)
        notifications.send_booking_confirmation_to_customer(db_booking, service, owner, request.state.lang)
    except Exception as e:
        print(f"Error sending notification: {e}")
        # Log error but don't prevent booking completion

    return templates.TemplateResponse(
        "booking_confirmation.html",
        {
            "request": request,
            "booking": db_booking,
            "service": service,
            "owner": owner,
            "lang": request.state.lang,
            "LANGUAGES": LANGUAGES,
            "_": _
        }
    )

# --- Owner Dashboard ---
@app.get("/dashboard", response_class=HTMLResponse, tags=["Owner Dashboard"])
async def owner_dashboard(
    request: Request,
    current_owner: models.Owner = Depends(security.get_current_active_owner),
    db: Session = Depends(get_db)
):
    _ = request.state.gettext
    
    upcoming_bookings = db.query(models.Booking).filter(
        models.Booking.owner_id == current_owner.id,
        models.Booking.date >= date.today()
    ).order_by(models.Booking.date, models.Booking.time).all()

    # Get services for the owner
    owner_services = db.query(models.Service).filter(models.Service.owner_id == current_owner.id).all()

    # Get analytics data
    monthly_bookings_data = analytics.get_monthly_bookings_data(db, current_owner.id)
    popular_services_data = analytics.get_popular_services_data(db, current_owner.id)

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "owner": current_owner,
            "upcoming_bookings": upcoming_bookings,
            "services": owner_services,
            "monthly_bookings_data": json.dumps(monthly_bookings_data), # Pass as JSON string for JS
            "popular_services_data": json.dumps(popular_services_data), # Pass as JSON string for JS
            "lang": request.state.lang,
            "LANGUAGES": LANGUAGES,
            "_": _
        }
    )

@app.get("/api/analytics/monthly_bookings", response_model=List[Dict[str, Any]], tags=["Analytics"])
@cache(expire=60 * 60) # Cache for 1 hour
async def get_monthly_bookings_analytics(
    current_owner: schemas.Owner = Depends(security.get_current_active_owner),
    db: Session = Depends(get_db)
):
    return analytics.get_monthly_bookings_data(db, current_owner.id)

@app.get("/api/analytics/popular_services", response_model=List[Dict[str, Any]], tags=["Analytics"])
@cache(expire=60 * 60) # Cache for 1 hour
async def get_popular_services_analytics(
    current_owner: schemas.Owner = Depends(security.get_current_active_owner),
    db: Session = Depends(get_db)
):
    return analytics.get_popular_services_data(db, current_owner.id)

@app.get("/admin/cache-stats", response_model=Dict[str, Any], tags=["Admin"])
async def get_cache_statistics(
    current_owner: schemas.Owner = Depends(security.get_current_active_owner) # Only logged-in owners can view
):
    """Return cache hit/miss statistics."""
    total = cache_stats["hits"] + cache_stats["misses"]
    hit_rate = 0.0
    if total > 0:
        hit_rate = cache_stats["hits"] / total
    return {
        "hits": cache_stats["hits"],
        "misses": cache_stats["misses"],
        "total": total,
        "hit_rate": round(hit_rate, 4)
    }

# --- Subscription Management (Stripe) ---
@app.post("/create-checkout-session", tags=["Subscription"])
async def create_checkout_session(
    request: Request,
    current_owner: models.Owner = Depends(security.get_current_active_owner),
    db: Session = Depends(get_db)
):
    _ = get_translator(current_owner.lang if current_owner.lang else DEFAULT_LANGUAGE)
    
    try:
        checkout_session = stripe.checkout.Session.create(
            line_items=[
                {
                    'price': settings.STRIPE_PREMIUM_PRICE_ID,
                    'quantity': 1,
                },
            ],
            mode='subscription',
            success_url=request.url_for('owner_dashboard')._url + "?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=request.url_for('owner_dashboard')._url + "?cancelled=true",
            customer_email=current_owner.email,
            client_reference_id=str(current_owner.id)
        )
        return {"url": checkout_session.url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/stripe-webhook", tags=["Subscription"])
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get('stripe-signature')

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError as e:
        # Invalid payload
        raise HTTPException(status_code=400, detail=str(e))
    except stripe.error.SignatureVerificationError as e:
        # Invalid signature
        raise HTTPException(status_code=400, detail=str(e))

    # Handle the event
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        owner_id = session.get('client_reference_id')
        customer_email = session.get('customer_details', {}).get('email')
        subscription_id = session.get('subscription')
        
        if owner_id:
            owner = db.query(models.Owner).filter(models.Owner.id == int(owner_id)).first()
            if owner:
                owner.is_premium = True
                owner.stripe_customer_id = session.get('customer')
                owner.stripe_subscription_id = subscription_id
                db.add(owner)
                db.commit()
                # Optionally send a welcome email for premium
                # notifications.send_premium_welcome(owner)
    elif event['type'] == 'customer.subscription.deleted':
        subscription = event['data']['object']
        owner = db.query(models.Owner).filter(models.Owner.stripe_subscription_id == subscription.id).first()
        if owner:
            owner.is_premium = False
            owner.stripe_subscription_id = None
            db.add(owner)
            db.commit()
            # notifications.send_subscription_cancelled(owner)
    # ... handle other event types like 'invoice.payment_succeeded', 'invoice.payment_failed'

    return {"status": "success"}

# --- Customer Accounts ---
@app.post("/customer/register", response_model=schemas.Customer, tags=["Customer Auth"])
async def register_customer(customer: schemas.CustomerCreate, db: Session = Depends(get_db)):
    db_customer = db.query(models.Customer).filter(models.Customer.email == customer.email).first()
    if db_customer:
        raise HTTPException(status_code=400, detail="Email already registered")
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

@app.post("/customer/token", response_model=schemas.Token, tags=["Customer Auth"])
async def login_for_customer_access_token(
    request: Request,
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    customer = security.authenticate_customer(db, form_data.username, form_data.password)
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=request.state.gettext("Incorrect email or password"),
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": customer.email, "user_type": "customer"}, expires_delta=access_token_expires
    )
    response.set_cookie(
        key="customer_access_token",
        value=f"Bearer {access_token}",
        httponly=True,
        max_age=access_token_expires.total_seconds(),
        samesite="Lax",
        secure=True
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/customer/me", response_model=schemas.Customer, tags=["Customer Auth"])
async def read_customer_me(current_customer: schemas.Customer = Depends(security.get_current_active_customer)):
    return current_customer

@app.put("/customer/profile", response_model=schemas.Customer, tags=["Customer Management"])
async def update_customer_profile(
    customer_update: schemas.CustomerUpdate,
    current_customer: models.Customer = Depends(security.get_current_active_customer),
    db: Session = Depends(get_db)
):
    try:
        for field, value in customer_update.dict(exclude_unset=True).items():
            setattr(current_customer, field, value)
        db.add(current_customer)
        db.commit()
        db.refresh(current_customer)
        return current_customer
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error updating customer profile: {e}")

# --- Review/Rating System ---
@app.post("/reviews/{owner_username}", response_model=schemas.Review, tags=["Reviews"])
async def submit_review(
    owner_username: str,
    review_data: schemas.ReviewCreate,
    current_customer: models.Customer = Depends(security.get_current_active_customer),
    db: Session = Depends(get_db)
):
    owner = db.query(models.Owner).filter(models.Owner.username == owner_username).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")
    
    # Check if customer has booked with this owner before (optional validation)
    # booking_exists = db.query(models.Booking).filter(
    #     models.Booking.owner_id == owner.id,
    #     models.Booking.customer_email == current_customer.email
    # ).first()
    # if not booking_exists:
    #     raise HTTPException(status_code=403, detail="Only customers who have booked can leave reviews.")

    db_review = models.Review(
        owner_id=owner.id,
        customer_id=current_customer.id,
        rating=review_data.rating,
        comment=review_data.comment
    )
    db.add(db_review)
    db.commit()
    db.refresh(db_review)
    return db_review

@app.get("/api/reviews/{owner_username}", response_model=List[schemas.Review], tags=["Reviews"])
async def get_reviews_for_owner(owner_username: str, db: Session = Depends(get_db)):
    owner = db.query(models.Owner).filter(models.Owner.username == owner_username).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")
    
    reviews = db.query(models.Review).filter(models.Review.owner_id == owner.id).all()
    return reviews


# --- Admin Panel (Basic CRUD for Owners, Services, Bookings) ---
@app.get("/admin/owners", response_model=List[schemas.Owner], tags=["Admin"])
async def admin_list_owners(
    skip: int = 0, limit: int = 100,
    current_owner: models.Owner = Depends(security.get_current_active_owner), # Assuming an owner can be an admin for now
    db: Session = Depends(get_db)
):
    # In a real app, you'd have a dedicated admin user role check
    # For now, let's assume current_owner being logged in is enough for this placeholder
    owners = db.query(models.Owner).offset(skip).limit(limit).all()
    return owners

@app.get("/admin/owner/{owner_id}", response_model=schemas.Owner, tags=["Admin"])
async def admin_get_owner(
    owner_id: int,
    current_owner: models.Owner = Depends(security.get_current_active_owner),
    db: Session = Depends(get_db)
):
    owner = db.query(models.Owner).filter(models.Owner.id == owner_id).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")
    return owner

@app.put("/admin/owner/{owner_id}", response_model=schemas.Owner, tags=["Admin"])
async def admin_update_owner(
    owner_id: int,
    owner_update: schemas.OwnerUpdate, # Use general owner update schema
    current_owner: models.Owner = Depends(security.get_current_active_owner),
    db: Session = Depends(get_db)
):
    db_owner = db.query(models.Owner).filter(models.Owner.id == owner_id).first()
    if not db_owner:
        raise HTTPException(status_code=404, detail="Owner not found")
    
    for field, value in owner_update.dict(exclude_unset=True).items():
        setattr(db_owner, field, value)
    db.add(db_owner)
    db.commit()
    db.refresh(db_owner)
    return db_owner

@app.delete("/admin/owner/{owner_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Admin"])
async def admin_delete_owner(
    owner_id: int,
    current_owner: models.Owner = Depends(security.get_current_active_owner),
    db: Session = Depends(get_db)
):
    db_owner = db.query(models.Owner).filter(models.Owner.id == owner_id).first()
    if not db_owner:
        raise HTTPException(status_code=404, detail="Owner not found")
    db.delete(db_owner)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

# Admin: Manage Services (list, update, delete)
@app.get("/admin/owner/{owner_id}/services", response_model=List[schemas.Service], tags=["Admin"])
async def admin_list_owner_services(
    owner_id: int,
    current_owner: models.Owner = Depends(security.get_current_active_owner),
    db: Session = Depends(get_db)
):
    services = db.query(models.Service).filter(models.Service.owner_id == owner_id).all()
    return services

# Admin: Manage Bookings (list, update, delete)
@app.get("/admin/owner/{owner_id}/bookings", response_model=List[schemas.Booking], tags=["Admin"])
async def admin_list_owner_bookings(
    owner_id: int,
    current_owner: models.Owner = Depends(security.get_current_active_owner),
    db: Session = Depends(get_db)
):
    bookings = db.query(models.Booking).filter(models.Booking.owner_id == owner_id).all()
    return bookings


# --- Root/Home Page (optional, for simple landing) ---
@app.get("/", response_class=HTMLResponse, tags=["General"])
async def read_root(request: Request):
    _ = request.state.gettext
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "lang": request.state.lang,
            "LANGUAGES": LANGUAGES,
            "_": _
        }
    )