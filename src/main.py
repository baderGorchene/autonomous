from fastapi import FastAPI, Depends, HTTPException, status, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.security import OAuth2PasswordRequestForm, HTTPBearer
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import timedelta, date, datetime, time
import secrets
from typing import List, Optional, Dict, Any
import json
import calendar
from gettext import gettext as _ # For i18n

# For caching
from redis import asyncio as aioredis
from redis.asyncio.connection import ConnectionPool
from fastapi_cache import FastAPICache
from fastapi_cache.backends.redis import RedisBackend
from fastapi_cache.decorator import cache
from starlette.middleware.sessions import SessionMiddleware

from . import models, schemas, crud, security, notifications, availability_utils, analytics, stripe_utils
from .database import SessionLocal, engine
from .config import settings

models.Base.metadata.create_all(bind=engine)

app = FastAPI()

app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

templates = Jinja2Templates(directory="templates")

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Caching setup
redis_pool = ConnectionPool.from_url(
    settings.REDIS_URL,
    max_connections=10,
    decode_responses=False,
)
redis_client = aioredis.Redis(connection_pool=redis_pool)

@app.on_event("startup")
async def startup_event():
    FastAPICache.init(RedisBackend(redis_client), prefix="fastapi-cache")
    print(f"FastAPI Cache initialized with Redis at {settings.REDIS_URL}")

# Cache statistics tracking
cache_stats = {"hits": 0, "misses": 0}

@app.middleware("http")
async def track_cache_stats(request: Request, call_next):
    """Middleware to track cache hit/miss ratios."""
    response = await call_next(request)
    cache_header = response.headers.get("X-FastAPI-Cache")
    if cache_header == "HIT":
        cache_stats["hits"] += 1
    elif cache_header == "MISS":
        cache_stats["misses"] += 1
    return response

@app.get("/admin/cache-stats", tags=["Admin"])
async def get_cache_statistics():
    """Return cache hit/miss statistics."""
    total = cache_stats["hits"] + cache_stats["misses"]
    hit_rate = 0
    if total > 0:
        hit_rate = cache_stats["hits"] / total
    return {
        "hits": cache_stats["hits"],
        "misses": cache_stats["misses"],
        "total": total,
        "hit_rate": hit_rate,
        "backend": "Redis"
    }

# --- Internationalization (i18n) Helper ---
@app.get("/set-language/{lang_code}")
async def set_language(lang_code: str, response: Response):
    response.set_cookie(key="lang", value=lang_code, httponly=False, expires=3600 * 24 * 30)
    return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)

# --- Authentication and Authorization ---
@app.post("/token", response_model=schemas.Token, tags=["Auth"])
async def login_for_access_token(db: Session = Depends(get_db), form_data: OAuth2PasswordRequestForm = Depends()):
    user = security.authenticate_owner(db, username=form_data.username, password=form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_("Incorrect username or password"),
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": user.username, "is_owner": True}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/customer-token", response_model=schemas.Token, tags=["Auth"])
async def login_for_customer_access_token(db: Session = Depends(get_db), form_data: OAuth2PasswordRequestForm = Depends()):
    customer = security.authenticate_customer(db, email=form_data.username, password=form_data.password)
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_("Incorrect email or password"),
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": customer.email, "is_owner": False}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/signup", response_model=schemas.Owner, tags=["Auth"])
async def create_owner_signup(owner: schemas.OwnerCreate, db: Session = Depends(get_db)):
    db_owner = crud.get_owner_by_username(db, username=owner.username)
    if db_owner:
        raise HTTPException(status_code=400, detail=_("Username already registered"))
    db_owner = crud.get_owner_by_email(db, email=owner.email)
    if db_owner:
        raise HTTPException(status_code=400, detail=_("Email already registered"))
    return crud.create_owner(db=db, owner=owner)

@app.post("/customers/register", response_model=schemas.Customer, tags=["Customer Accounts"])
async def register_customer(customer: schemas.CustomerCreate, db: Session = Depends(get_db)):
    db_customer = crud.get_customer_by_email(db, email=customer.email)
    if db_customer:
        raise HTTPException(status_code=400, detail=_("Email already registered"))
    return crud.create_customer(db=db, customer=customer)

# --- Root --- 
@app.get("/", response_class=RedirectResponse, include_in_schema=False)
async def read_root():
    return RedirectResponse(url="/login")

@app.get("/login", response_class=HTMLResponse, tags=["Auth"])
async def login_page(request: Request):
    lang = request.cookies.get("lang", "en")
    request.state.lang = lang
    return templates.TemplateResponse("login.html", {"request": request, "lang": lang})

# --- Public Booking Page ---
@app.get("/book/{owner_username}", response_class=HTMLResponse, tags=["Public"])
@cache(expire=300, namespace="booking_pages") # Cache public booking page for 5 minutes
async def get_booking_page(owner_username: str, request: Request, db: Session = Depends(get_db)):
    lang = request.cookies.get("lang", "en")
    request.state.lang = lang

    owner = crud.get_owner_by_username(db, username=owner_username)
    if not owner:
        raise HTTPException(status_code=404, detail=_("Owner not found"))

    services = crud.get_services_by_owner(db, owner_id=owner.id)

    # Fetch initial available slots for today for the first service if available
    today = date.today()
    initial_available_slots = []
    if services:
        first_service = services[0]
        slots = availability_utils.get_available_slots_for_day(
            db, owner.id, first_service.id, today, first_service.duration_minutes
        )
        initial_available_slots = [s.strftime("%H:%M") for s in slots]

    # Fetch existing reviews for the owner
    reviews = crud.get_reviews_for_owner(db, owner_id=owner.id)

    return templates.TemplateResponse("booking_page.html", {
        "request": request,
        "owner": owner,
        "services": services,
        "today": today,
        "available_slots_json": json.dumps(initial_available_slots),
        "lang": lang,
        "reviews": reviews
    })

@app.get("/api/book/{owner_id}/services/{service_id}/available_slots", response_model=List[time], tags=["Public"])
@cache(expire=60, namespace="available_slots") # Cache available slots for 1 minute
async def get_service_available_slots(
    owner_id: int,
    service_id: int,
    target_date: date,
    db: Session = Depends(get_db)
):
    owner = crud.get_owner(db, owner_id=owner_id)
    service = crud.get_service(db, service_id=service_id)

    if not owner or not service or service.owner_id != owner_id:
        raise HTTPException(status_code=404, detail=_("Owner or service not found"))

    slots = availability_utils.get_available_slots_for_day(
        db, owner_id, service_id, target_date, service.duration_minutes
    )
    return slots

@app.post("/book/{owner_username}/submit", response_class=HTMLResponse, tags=["Public"])
async def submit_booking(
    owner_username: str,
    customer_booking: schemas.CustomerBookingCreate,
    request: Request,
    db: Session = Depends(get_db)
):
    lang = request.cookies.get("lang", "en")
    request.state.lang = lang

    owner = crud.get_owner_by_username(db, username=owner_username)
    if not owner:
        raise HTTPException(status_code=404, detail=_("Owner not found"))

    service = crud.get_service(db, service_id=customer_booking.service_id)
    if not service or service.owner_id != owner.id:
        raise HTTPException(status_code=404, detail=_("Service not found for this owner"))

    # Validate the requested slot is actually available
    requested_time_dt = datetime.strptime(customer_booking.time, "%H:%M").time()
    available_slots = availability_utils.get_available_slots_for_day(
        db, owner.id, service.id, customer_booking.date, service.duration_minutes
    )

    if requested_time_dt not in available_slots:
        raise HTTPException(status_code=400, detail=_("Requested time slot is not available. Please choose another."))

    try:
        booking = crud.create_booking(db=db, booking=customer_booking, owner_id=owner.id, service_id=service.id)

        # Send notifications
        notifications.send_booking_confirmation_email(owner, customer_booking, service, booking)
        notifications.send_booking_confirmation_whatsapp(owner, customer_booking, service, booking)

        # Clear relevant caches as bookings change availability
        await FastAPICache.clear(namespace="available_slots")
        await FastAPICache.clear(namespace="owner_dashboards") # Dashboard might show booking counts

        return templates.TemplateResponse("booking_confirmation.html", {
            "request": request,
            "owner": owner,
            "booking": booking,
            "service": service,
            "lang": lang
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- Customer Reviews ---
@app.post("/reviews/{owner_id}/submit", response_model=schemas.Review, tags=["Reviews"])
async def submit_review(
    owner_id: int,
    review_data: schemas.ReviewCreate,
    db: Session = Depends(get_db),
    current_customer: models.Customer = Depends(security.get_current_active_customer)
):
    owner = crud.get_owner(db, owner_id=owner_id)
    if not owner:
        raise HTTPException(status_code=404, detail=_("Owner not found"))
    
    # Check if the customer has a booking with this owner to allow review
    has_booked = crud.get_booking_by_customer_and_owner(db, customer_id=current_customer.id, owner_id=owner_id)
    if not has_booked:
        raise HTTPException(status_code=403, detail=_("You can only review businesses you have booked with."))

    db_review = crud.create_review(db, review=review_data, owner_id=owner_id, customer_id=current_customer.id)
    return db_review

@app.get("/reviews/{owner_id}", response_model=List[schemas.Review], tags=["Reviews"])
@cache(expire=300, namespace="owner_reviews") # Cache reviews for 5 minutes
async def get_reviews_for_owner(owner_id: int, db: Session = Depends(get_db)):
    reviews = crud.get_reviews_for_owner(db, owner_id=owner_id)
    return reviews

# --- Owner Dashboard ---
@app.get("/dashboard", response_class=HTMLResponse, tags=["Owner"])
@cache(expire=60, namespace="owner_dashboards", key_builder=lambda f, *args, **kwargs: f"{kwargs['current_owner'].id}")
async def owner_dashboard(request: Request, db: Session = Depends(get_db), current_owner: models.Owner = Depends(security.get_current_active_owner)):
    lang = request.cookies.get("lang", "en")
    request.state.lang = lang

    upcoming_bookings = crud.get_upcoming_bookings_for_owner(db, owner_id=current_owner.id)

    # Analytics data (fetched via API for better caching control)
    # monthly_bookings = analytics.get_monthly_bookings_data(db, owner_id=current_owner.id)
    # popular_services = analytics.get_popular_services_data(db, owner_id=current_owner.id)

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "owner": current_owner,
        "upcoming_bookings": upcoming_bookings,
        "lang": lang
    })

@app.get("/api/dashboard/analytics", tags=["Owner"])
@cache(expire=300, namespace="owner_analytics", key_builder=lambda f, *args, **kwargs: f"{kwargs['current_owner'].id}")
async def get_owner_analytics(db: Session = Depends(get_db), current_owner: models.Owner = Depends(security.get_current_active_owner)):
    monthly_bookings = analytics.get_monthly_bookings_data(db, owner_id=current_owner.id)
    popular_services = analytics.get_popular_services_data(db, owner_id=current_owner.id)
    return {
        "monthly_bookings": monthly_bookings,
        "popular_services": popular_services
    }

@app.get("/owners/me", response_model=schemas.Owner, tags=["Owner"])
async def read_owner_me(current_owner: models.Owner = Depends(security.get_current_active_owner)):
    return current_owner

@app.put("/owners/me/profile", response_model=schemas.Owner, tags=["Owner"])
async def update_owner_profile(
    owner_update: schemas.OwnerUpdate,
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(security.get_current_active_owner)
):
    updated_owner = crud.update_owner(db, owner_id=current_owner.id, owner=owner_update)
    if not updated_owner:
        raise HTTPException(status_code=404, detail=_("Owner not found"))
    await FastAPICache.clear(namespace="owner_dashboards", key=str(current_owner.id)) # Clear dashboard cache
    return updated_owner

# --- Service Management ---
@app.post("/services", response_model=schemas.Service, tags=["Owner Services"])
async def create_service_for_owner(
    service: schemas.ServiceCreate,
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(security.get_current_active_owner)
):
    await FastAPICache.clear(namespace="booking_pages") # New service might affect booking page
    return crud.create_owner_service(db=db, service=service, owner_id=current_owner.id)

@app.get("/services", response_model=List[schemas.Service], tags=["Owner Services"])
async def read_owner_services(
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(security.get_current_active_owner)
):
    return crud.get_services_by_owner(db=db, owner_id=current_owner.id)

@app.get("/services/{service_id}", response_model=schemas.Service, tags=["Owner Services"])
async def read_service(
    service_id: int,
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(security.get_current_active_owner)
):
    service = crud.get_service(db, service_id=service_id)
    if not service or service.owner_id != current_owner.id:
        raise HTTPException(status_code=404, detail=_("Service not found"))
    return service

@app.put("/services/{service_id}", response_model=schemas.Service, tags=["Owner Services"])
async def update_service(
    service_id: int,
    service_update: schemas.ServiceUpdate,
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(security.get_current_active_owner)
):
    db_service = crud.update_service(db, service_id=service_id, service=service_update, owner_id=current_owner.id)
    if not db_service:
        raise HTTPException(status_code=404, detail=_("Service not found or not owned by current owner"))
    await FastAPICache.clear(namespace="booking_pages")
    await FastAPICache.clear(namespace="available_slots")
    return db_service

@app.delete("/services/{service_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Owner Services"])
async def delete_service(
    service_id: int,
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(security.get_current_active_owner)
):
    success = crud.delete_service(db, service_id=service_id, owner_id=current_owner.id)
    if not success:
        raise HTTPException(status_code=404, detail=_("Service not found or not owned by current owner"))
    await FastAPICache.clear(namespace="booking_pages")
    await FastAPICache.clear(namespace="available_slots")
    return Response(status_code=status.HTTP_204_NO_CONTENT)

# --- Availability Management ---
@app.post("/availability", response_model=schemas.Availability, tags=["Owner Availability"])
async def create_availability_for_owner(
    availability: schemas.AvailabilityCreate,
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(security.get_current_active_owner)
):
    await FastAPICache.clear(namespace="available_slots")
    return crud.create_owner_availability(db=db, availability=availability, owner_id=current_owner.id)

@app.get("/availability", response_model=List[schemas.Availability], tags=["Owner Availability"])
async def read_owner_availabilities(
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(security.get_current_active_owner)
):
    return crud.get_availabilities_by_owner(db=db, owner_id=current_owner.id)

@app.put("/availability/{availability_id}", response_model=schemas.Availability, tags=["Owner Availability"])
async def update_availability(
    availability_id: int,
    availability_update: schemas.AvailabilityUpdate,
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(security.get_current_active_owner)
):
    db_availability = crud.update_availability(db, availability_id=availability_id, availability=availability_update, owner_id=current_owner.id)
    if not db_availability:
        raise HTTPException(status_code=404, detail=_("Availability not found or not owned by current owner"))
    await FastAPICache.clear(namespace="available_slots")
    return db_availability

@app.delete("/availability/{availability_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Owner Availability"])
async def delete_availability(
    availability_id: int,
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(security.get_current_active_owner)
):
    success = crud.delete_availability(db, availability_id=availability_id, owner_id=current_owner.id)
    if not success:
        raise HTTPException(status_code=404, detail=_("Availability not found or not owned by current owner"))
    await FastAPICache.clear(namespace="available_slots")
    return Response(status_code=status.HTTP_204_NO_CONTENT)

# --- Customer Account Management ---
@app.get("/customers/me", response_model=schemas.Customer, tags=["Customer Accounts"])
async def read_customer_me(current_customer: models.Customer = Depends(security.get_current_active_customer)):
    return current_customer

@app.put("/customers/me/profile", response_model=schemas.Customer, tags=["Customer Accounts"])
async def update_customer_profile(
    customer_update: schemas.CustomerUpdate,
    db: Session = Depends(get_db),
    current_customer: models.Customer = Depends(security.get_current_active_customer)
):
    updated_customer = crud.update_customer(db, customer_id=current_customer.id, customer=customer_update)
    if not updated_customer:
        raise HTTPException(status_code=404, detail=_("Customer not found"))
    return updated_customer

# --- Subscription Management ---
@app.post("/create-checkout-session", tags=["Subscription"])
async def create_checkout_session(db: Session = Depends(get_db), current_owner: models.Owner = Depends(security.get_current_active_owner)):
    return stripe_utils.create_stripe_checkout_session(db, current_owner)

@app.post("/stripe-webhook", tags=["Subscription"])
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get('stripe-signature')

    event = None
    try:
        event = stripe_utils.stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError as e:
        # Invalid payload
        raise HTTPException(status_code=400, detail=str(e))
    except stripe_utils.stripe.error.SignatureVerificationError as e:
        # Invalid signature
        raise HTTPException(status_code=400, detail=str(e))

    # Handle the event
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        stripe_utils.handle_checkout_session_completed(db, session)
    elif event['type'] == 'customer.subscription.updated':
        subscription = event['data']['object']
        stripe_utils.handle_subscription_updated(db, subscription)
    elif event['type'] == 'customer.subscription.deleted':
        subscription = event['data']['object']
        stripe_utils.handle_subscription_deleted(db, subscription)
    # ... handle other event types

    return JSONResponse(content={'status': 'success'})

@app.get("/subscription", response_class=HTMLResponse, tags=["Subscription"])
async def subscription_page(request: Request, db: Session = Depends(get_db), current_owner: models.Owner = Depends(security.get_current_active_owner)):
    lang = request.cookies.get("lang", "en")
    request.state.lang = lang
    
    subscription_status = crud.get_owner_subscription_status(db, current_owner.id)
    is_premium = subscription_status == models.SubscriptionStatus.ACTIVE
    return templates.TemplateResponse("subscription.html", {
        "request": request,
        "owner": current_owner,
        "is_premium": is_premium,
        "subscription_status": subscription_status.value,
        "lang": lang
    })

# --- Admin Panel ---
@app.get("/admin/owners", response_model=List[schemas.Owner], tags=["Admin"])
async def admin_list_owners(db: Session = Depends(get_db), skip: int = 0, limit: int = 100, admin: models.Admin = Depends(security.get_current_active_admin)):
    owners = crud.get_owners(db, skip=skip, limit=limit)
    return owners

@app.get("/admin/owners/{owner_id}", response_model=schemas.Owner, tags=["Admin"])
async def admin_get_owner(owner_id: int, db: Session = Depends(get_db), admin: models.Admin = Depends(security.get_current_active_admin)):
    owner = crud.get_owner(db, owner_id=owner_id)
    if not owner:
        raise HTTPException(status_code=404, detail=_("Owner not found"))
    return owner

@app.put("/admin/owners/{owner_id}", response_model=schemas.Owner, tags=["Admin"])
async def admin_update_owner(
    owner_id: int,
    owner_update: schemas.OwnerUpdate,
    db: Session = Depends(get_db),
    admin: models.Admin = Depends(security.get_current_active_admin)
):
    updated_owner = crud.update_owner(db, owner_id=owner_id, owner=owner_update)
    if not updated_owner:
        raise HTTPException(status_code=404, detail=_("Owner not found"))
    await FastAPICache.clear(namespace="owner_dashboards", key=str(owner_id)) # Clear dashboard cache
    await FastAPICache.clear(namespace="booking_pages") # Owner profile changes might affect public page
    return updated_owner

@app.delete("/admin/owners/{owner_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Admin"])
async def admin_delete_owner(owner_id: int, db: Session = Depends(get_db), admin: models.Admin = Depends(security.get_current_active_admin)):
    success = crud.delete_owner(db, owner_id=owner_id)
    if not success:
        raise HTTPException(status_code=404, detail=_("Owner not found"))
    await FastAPICache.clear(namespace="owner_dashboards", key=str(owner_id))
    await FastAPICache.clear(namespace="booking_pages")
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@app.get("/admin/services", response_model=List[schemas.Service], tags=["Admin"])
async def admin_list_services(db: Session = Depends(get_db), skip: int = 0, limit: int = 100, admin: models.Admin = Depends(security.get_current_active_admin)):
    services = crud.get_services(db, skip=skip, limit=limit)
    return services

@app.get("/admin/bookings", response_model=List[schemas.Booking], tags=["Admin"])
async def admin_list_bookings(db: Session = Depends(get_db), skip: int = 0, limit: int = 100, admin: models.Admin = Depends(security.get_current_active_admin)):
    bookings = crud.get_bookings(db, skip=skip, limit=limit)
    return bookings

# Health check endpoint
@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "ok", "message": "BookSlot API is running"}
