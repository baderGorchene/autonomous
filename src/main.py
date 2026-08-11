import uvicorn
from fastapi import FastAPI, Depends, HTTPException, Request, Response, status, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import PlainTextResponse
from starlette.background import BackgroundTasks
from datetime import timedelta, date, datetime, time
from typing import List, Dict, Any, Optional

from redis.asyncio import Redis as AsyncRedis
from fastapi_limiter import FastAPILimiter
from fastapi_limiter.depends import RateLimiter
from pyrate_limiter import Duration, Limiter, Rate

from . import crud, models, schemas, security, database, notifications, analytics, availability_utils
from .config import settings
from .i18n import gettext_lazy as _, get_locale, activate_locale, get_translations, get_current_language
import stripe
import json
import calendar

app = FastAPI(title="BookSlot API")

app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' 'unsafe-inline' https://js.stripe.com; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; img-src 'self' data:; font-src 'self' https://fonts.gstatic.com; connect-src 'self' https://api.stripe.com; frame-src https://js.stripe.com;"
        return response

app.add_middleware(SecurityHeadersMiddleware)

async def rate_limit_exceeded_callback(request: Request, response: Response, pcall):
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail={
            "error": "rate_limit_exceeded",
            "message": "You have exceeded the rate limit. Please try again later.",
            "path": request.url.path,
            "retry_after": pcall.args[0].limit.period
        },
        headers={"Retry-After": str(pcall.args[0].limit.period)}
    )

@app.on_event("startup")
async def startup():
    database.create_db_and_tables()
    redis_client = AsyncRedis.from_url(settings.REDIS_URL, encoding="utf8", decode_responses=True)
    await FastAPILimiter.init(redis_client, prefix="fastapi-limiter", callback=rate_limit_exceeded_callback)
    stripe.api_key = settings.STRIPE_SECRET_KEY

@app.on_event("shutdown")
async def shutdown():
    pass

def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

templates = Jinja2Templates(directory="templates")

@app.middleware("http")
async def setup_i18n(request: Request, call_next):
    lang = request.session.get("lang", "en")
    activate_locale(lang)
    request.state.gettext = get_translations(lang)
    response = await call_next(request)
    return response

auth_rate_limit = Limiter(Rate(5, Duration.MINUTE))
booking_submission_rate_limit = Limiter(Rate(10, Duration.MINUTE))

@app.get("/health", response_class=PlainTextResponse, tags=["Monitoring"])
async def health_check():
    return "OK"

@app.post("/owner/signup", response_model=schemas.Owner, status_code=status.HTTP_201_CREATED, tags=["Owner"],
          dependencies=[Depends(RateLimiter(auth_rate_limit))])
async def create_owner(owner: schemas.OwnerCreate, db: Session = Depends(get_db)):
    db_owner = crud.get_owner_by_email(db, email=owner.email)
    if db_owner:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_("Email already registered"))
    hashed_password = security.get_password_hash(owner.password)
    db_owner = crud.create_owner(db=db, owner=owner, hashed_password=hashed_password)
    return db_owner

@app.post("/owner/login", response_model=schemas.Token, tags=["Owner"],
          dependencies=[Depends(RateLimiter(auth_rate_limit))])
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    owner = security.authenticate_owner(db, form_data.username, form_data.password)
    if not owner:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_("Incorrect email or password"),
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": owner.email, "user_id": str(owner.id), "user_type": "owner"}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/customer/signup", response_model=schemas.Customer, status_code=status.HTTP_201_CREATED, tags=["Customer"],
          dependencies=[Depends(RateLimiter(auth_rate_limit))])
async def create_customer(customer: schemas.CustomerCreate, db: Session = Depends(get_db)):
    db_customer = crud.get_customer_by_email(db, email=customer.email)
    if db_customer:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_("Email already registered"))
    hashed_password = security.get_password_hash(customer.password)
    db_customer = crud.create_customer(db=db, customer=customer, hashed_password=hashed_password)
    return db_customer

@app.post("/customer/login", response_model=schemas.Token, tags=["Customer"],
          dependencies=[Depends(RateLimiter(auth_rate_limit))])
async def login_for_customer_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    customer = security.authenticate_customer(db, form_data.username, form_data.password)
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_("Incorrect email or password"),
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": customer.email, "user_id": str(customer.id), "user_type": "customer"}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/bookslot.app/{owner_name}", response_class=HTMLResponse, tags=["Public Booking"])
async def public_booking_page(request: Request, owner_name: str, db: Session = Depends(get_db)):
    owner = crud.get_owner_by_name(db, owner_name=owner_name)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Owner not found"))

    services = crud.get_services_by_owner(db, owner_id=owner.id)
    reviews = crud.get_reviews_for_owner(db, owner_id=owner.id)

    context = {
        "request": request,
        "owner": owner,
        "services": services,
        "current_date": date.today(),
        "today_str": date.today().isoformat(),
        "gettext": request.state.gettext,
        "lang": get_current_language(request),
        "reviews": reviews,
        "settings": settings
    }
    return templates.TemplateResponse("booking_page.html", context)

@app.post("/book", response_class=HTMLResponse, tags=["Public Booking"],
          dependencies=[Depends(RateLimiter(booking_submission_rate_limit))])
async def submit_booking(
    request: Request,
    owner_id: int = Form(...),
    service_id: int = Form(...),
    customer_name: str = Form(...),
    customer_email: str = Form(...),
    customer_phone: Optional[str] = Form(None),
    booking_date: date = Form(...),
    booking_time: str = Form(...),
    is_recurring: bool = Form(False),
    recurrence_type: Optional[models.RecurrenceType] = Form(None),
    recurrence_value: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    owner = crud.get_owner(db, owner_id=owner_id)
    service = crud.get_service(db, service_id=service_id)

    if not owner or not service or service.owner_id != owner.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Owner or service not found"))

    try:
        parsed_booking_time = datetime.strptime(booking_time, "%H:%M").time()
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_("Invalid time format"))

    available_slots = availability_utils.get_available_slots_for_day(
        db, owner_id, service_id, booking_date, service.duration_minutes
    )
    if parsed_booking_time not in available_slots:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_("Selected slot is not available"))

    try:
        if is_recurring:
            if not recurrence_type or not recurrence_value:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_("Recurrence details are required for recurring bookings"))

            booking = crud.create_recurring_booking(
                db=db,
                owner_id=owner_id,
                service_id=service_id,
                customer_name=customer_name,
                customer_email=customer_email,
                customer_phone=customer_phone,
                date=booking_date,
                time=parsed_booking_time,
                recurrence_type=recurrence_type,
                recurrence_value=recurrence_value
            )
        else:
            booking = crud.create_booking(
                db=db,
                owner_id=owner_id,
                service_id=service_id,
                customer_name=customer_name,
                customer_email=customer_email,
                customer_phone=customer_phone,
                date=booking_date,
                time=parsed_booking_time
            )

        background_tasks.add_task(
            notifications.send_booking_confirmation,
            owner_email=owner.email,
            owner_phone=owner.phone,
            customer_email=customer_email,
            customer_phone=customer_phone,
            booking=booking,
            service=service,
            owner_name=owner.name,
            locale=get_current_language(request)
        )

        context = {
            "request": request,
            "booking": booking,
            "owner": owner,
            "service": service,
            "gettext": request.state.gettext,
            "lang": get_current_language(request)
        }
        return templates.TemplateResponse("booking_confirmation.html", context)
    except Exception as e:
        print(f"Error creating booking: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=_("Failed to create booking"))

@app.get("/api/owner/{owner_id}/services/{service_id}/available-slots", response_model=List[str], tags=["Public Booking"])
async def get_available_slots(
    owner_id: int,
    service_id: int,
    selected_date: date,
    db: Session = Depends(get_db)
):
    service = crud.get_service(db, service_id=service_id)
    if not service or service.owner_id != owner_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Service not found for this owner"))

    slots = availability_utils.get_available_slots_for_day(
        db, owner_id, service_id, selected_date, service.duration_minutes
    )
    return [s.strftime("%H:%M") for s in slots]

@app.get("/owner/dashboard", response_class=HTMLResponse, tags=["Owner Dashboard"])
async def owner_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(security.get_current_active_owner)
):
    owner_id = current_owner.id
    upcoming_bookings = crud.get_upcoming_bookings_for_owner(db, owner_id)
    services = crud.get_services_by_owner(db, owner_id)
    
    monthly_bookings_data = analytics.get_monthly_bookings_data(db, owner_id)
    popular_services_data = analytics.get_popular_services_data(db, owner_id)

    context = {
        "request": request,
        "owner": current_owner,
        "upcoming_bookings": upcoming_bookings,
        "services": services,
        "monthly_bookings_data": json.dumps(monthly_bookings_data),
        "popular_services_data": json.dumps(popular_services_data),
        "gettext": request.state.gettext,
        "lang": get_current_language(request)
    }
    return templates.TemplateResponse("dashboard.html", context)

@app.post("/owner/profile", response_model=schemas.Owner, tags=["Owner Dashboard"])
async def update_owner_profile(
    owner_update: schemas.OwnerUpdate,
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(security.get_current_active_owner)
):
    updated_owner = crud.update_owner_profile(db, current_owner, owner_update)
    if not updated_owner:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_("Failed to update profile"))
    return updated_owner

@app.post("/owner/services", response_model=schemas.Service, status_code=status.HTTP_201_CREATED, tags=["Owner Dashboard"])
async def create_service(
    service: schemas.ServiceCreate,
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(security.get_current_active_owner)
):
    return crud.create_owner_service(db=db, service=service, owner_id=current_owner.id)

@app.put("/owner/services/{service_id}", response_model=schemas.Service, tags=["Owner Dashboard"])
async def update_service(
    service_id: int,
    service: schemas.ServiceUpdate,
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(security.get_current_active_owner)
):
    db_service = crud.get_service(db, service_id=service_id)
    if not db_service or db_service.owner_id != current_owner.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Service not found or not owned by you"))
    return crud.update_service(db=db, service=db_service, service_update=service)

@app.delete("/owner/services/{service_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Owner Dashboard"])
async def delete_service(
    service_id: int,
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(security.get_current_active_owner)
):
    db_service = crud.get_service(db, service_id=service_id)
    if not db_service or db_service.owner_id != current_owner.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Service not found or not owned by you"))
    crud.delete_service(db=db, service_id=service_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@app.post("/owner/availability", response_model=schemas.Availability, status_code=status.HTTP_201_CREATED, tags=["Owner Dashboard"])
async def create_availability(
    availability: schemas.AvailabilityCreate,
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(security.get_current_active_owner)
):
    return crud.create_owner_availability(db=db, availability=availability, owner_id=current_owner.id)

@app.put("/owner/availability/{availability_id}", response_model=schemas.Availability, tags=["Owner Dashboard"])
async def update_availability(
    availability_id: int,
    availability: schemas.AvailabilityUpdate,
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(security.get_current_active_owner)
):
    db_availability = crud.get_availability(db, availability_id=availability_id)
    if not db_availability or db_availability.owner_id != current_owner.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Availability not found or not owned by you"))
    return crud.update_availability(db=db, availability=db_availability, availability_update=availability)

@app.delete("/owner/availability/{availability_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Owner Dashboard"])
async def delete_availability(
    availability_id: int,
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(security.get_current_active_owner)
):
    db_availability = crud.get_availability(db, availability_id=availability_id)
    if not db_availability or db_availability.owner_id != current_owner.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Availability not found or not owned by you"))
    crud.delete_availability(db=db, availability_id=availability_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@app.get("/owner/subscription", response_class=HTMLResponse, tags=["Subscription"])
async def subscription_management_page(
    request: Request,
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(security.get_current_active_owner)
):
    subscription = crud.get_active_subscription_by_owner_id(db, current_owner.id)
    
    context = {
        "request": request,
        "owner": current_owner,
        "subscription": subscription,
        "gettext": request.state.gettext,
        "lang": get_current_language(request)
    }
    return templates.TemplateResponse("subscription_management.html", context)

@app.post("/create-checkout-session", tags=["Subscription"])
async def create_checkout_session(
    request: Request,
    price_id: str = Form(...),
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(security.get_current_active_owner)
):
    try:
        checkout_session = stripe.checkout.Session.create(
            customer_email=current_owner.email,
            line_items=[
                {
                    'price': price_id,
                    'quantity': 1,
                },
            ],
            mode='subscription',
            success_url=f"{settings.APP_BASE_URL}/owner/dashboard?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{settings.APP_BASE_URL}/owner/subscription",
            metadata={'owner_id': str(current_owner.id)}
        )
        return RedirectResponse(checkout_session.url, status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@app.post("/stripe-webhook", tags=["Stripe Webhook"])
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get('stripe-signature')

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except stripe.error.SignatureVerificationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        owner_id = int(session['metadata']['owner_id'])
        customer_id = session['customer']
        subscription_id = session['subscription']
        
        crud.create_or_update_subscription(db, owner_id, customer_id, subscription_id, models.SubscriptionStatus.ACTIVE)
    elif event['type'] == 'customer.subscription.deleted':
        subscription = event['data']['object']
        crud.update_subscription_status_by_stripe_sub_id(db, subscription['id'], models.SubscriptionStatus.CANCELLED)
    
    return JSONResponse(content={"status": "success"})

@app.post("/api/services/{service_id}/reviews", response_model=schemas.Review, status_code=status.HTTP_201_CREATED, tags=["Reviews"])
async def submit_review(
    service_id: int,
    review_create: schemas.ReviewCreate,
    db: Session = Depends(get_db),
    current_customer: models.Customer = Depends(security.get_current_active_customer)
):
    service = crud.get_service(db, service_id=service_id)
    if not service:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Service not found"))
    
    return crud.create_review(db, service_id=service_id, customer_id=current_customer.id, review_data=review_create)

@app.get("/api/services/{service_id}/reviews", response_model=List[schemas.Review], tags=["Reviews"])
async def get_reviews_for_service(service_id: int, db: Session = Depends(get_db)):
    service = crud.get_service(db, service_id=service_id)
    if not service:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Service not found"))
    return crud.get_reviews_for_service(db, service_id=service_id)

def get_current_active_admin(current_owner: models.Owner = Depends(security.get_current_active_owner)):
    if not current_owner.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_("Not authorized to access admin panel"))
    return current_owner

@app.get("/admin/dashboard", response_class=HTMLResponse, tags=["Admin Panel"])
async def admin_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.Owner = Depends(get_current_active_admin)
):
    owners = crud.get_owners(db)
    subscriptions = crud.get_all_subscriptions(db)
    
    context = {
        "request": request,
        "admin": current_admin,
        "owners": owners,
        "subscriptions": subscriptions,
        "gettext": request.state.gettext,
        "lang": get_current_language(request)
    }
    return templates.TemplateResponse("admin_dashboard.html", context)

@app.get("/admin/owners", response_model=List[schemas.Owner], tags=["Admin Panel"])
async def admin_get_owners(db: Session = Depends(get_db), current_admin: models.Owner = Depends(get_current_active_admin)):
    return crud.get_owners(db)

@app.get("/admin/owners/{owner_id}", response_model=schemas.Owner, tags=["Admin Panel"])
async def admin_get_owner(owner_id: int, db: Session = Depends(get_db), current_admin: models.Owner = Depends(get_current_active_admin)):
    owner = crud.get_owner(db, owner_id=owner_id)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Owner not found"))
    return owner

@app.put("/admin/owners/{owner_id}", response_model=schemas.Owner, tags=["Admin Panel"])
async def admin_update_owner(owner_id: int, owner_update: schemas.OwnerUpdate, db: Session = Depends(get_db), current_admin: models.Owner = Depends(get_current_active_admin)):
    db_owner = crud.get_owner(db, owner_id=owner_id)
    if not db_owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Owner not found"))
    return crud.update_owner_profile(db, db_owner, owner_update)

@app.delete("/admin/owners/{owner_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Admin Panel"])
async def admin_delete_owner(owner_id: int, db: Session = Depends(get_db), current_admin: models.Owner = Depends(get_current_active_admin)):
    crud.delete_owner(db, owner_id=owner_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@app.get("/admin/owners/{owner_id}/services", response_model=List[schemas.Service], tags=["Admin Panel"])
async def admin_get_owner_services(owner_id: int, db: Session = Depends(get_db), current_admin: models.Owner = Depends(get_current_active_admin)):
    return crud.get_services_by_owner(db, owner_id)

@app.get("/admin/owners/{owner_id}/bookings", response_model=List[schemas.Booking], tags=["Admin Panel"])
async def admin_get_owner_bookings(owner_id: int, db: Session = Depends(get_db), current_admin: models.Owner = Depends(get_current_active_admin)):
    return crud.get_bookings_for_owner(db, owner_id)

@app.post("/set-language", response_class=RedirectResponse, tags=["Internationalization"])
async def set_language(request: Request, lang: str = Form(...)):
    request.session["lang"] = lang
    return RedirectResponse(request.headers.get("referer", "/"), status_code=status.HTTP_303_SEE_OTHER)

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "gettext": request.state.gettext})