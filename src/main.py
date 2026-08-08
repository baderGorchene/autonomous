import os
import logging
from typing import List, Annotated, Optional
from datetime import datetime, timedelta

from fastapi import FastAPI, Depends, HTTPException, status, Request, Response
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import ValidationError # Import ValidationError

import stripe

from . import models, schemas, crud
from .database import SessionLocal, engine, get_db
from .security import authenticate_owner, create_access_token, get_current_owner, get_password_hash, verify_password
from .config import settings
from .notifications import send_booking_confirmation_email, send_owner_notification_email, send_owner_notification_whatsapp
from .i18n import get_locale, setup_jinja2_gettext_extension

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create database tables
models.Base.metadata.create_all(bind=engine)

app = FastAPI()

# Configure Stripe
stripe.api_key = settings.STRIPE_SECRET_KEY

# Setup static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Setup templates
templates = Jinja2Templates(directory="templates")
setup_jinja2_gettext_extension(app, templates)

# Dependency to get the database session
def get_db_dependency():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Middleware for i18n
@app.middleware("http")
async def i18n_middleware(request: Request, call_next):
    # Try to get language from query param first, then header, then default
    lang = request.query_params.get("lang")
    if not lang:
        lang = request.headers.get("Accept-Language", settings.DEFAULT_LOCALE).split(',')[0].split('-')[0]
    
    # Basic validation for supported locales
    if lang not in ["en", "ar", "fr"]:
        lang = settings.DEFAULT_LOCALE # Fallback to default if unsupported

    request.state.locale = lang
    request.state.gettext = get_locale(lang)
    response = await call_next(request)
    return response

# Root redirect to dashboard or login
@app.get("/", response_class=RedirectResponse, include_in_schema=False)
async def root():
    return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)

@app.get("/login", response_class=HTMLResponse)
async def login_form(request: Request):
    _ = request.state.gettext
    return templates.TemplateResponse("login.html", {"request": request, "error": None})

@app.post("/login", response_class=HTMLResponse)
async def login_for_access_token(request: Request, db: Session = Depends(get_db_dependency), form_data: OAuth2PasswordRequestForm = Depends()):
    _ = request.state.gettext
    owner = authenticate_owner(db, form_data.username, form_data.password)
    if not owner:
        return templates.TemplateResponse("login.html", {"request": request, "error": _("Incorrect email or password")})
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": owner.email}, expires_delta=access_token_expires
    )
    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    response.set_cookie(key="access_token", value=f"Bearer {access_token}", httponly=True)
    return response

@app.get("/signup", response_class=HTMLResponse)
async def signup_form(request: Request):
    _ = request.state.gettext
    return templates.TemplateResponse("signup.html", {"request": request, "error": None})

@app.post("/signup", response_class=HTMLResponse)
async def signup_owner(request: Request, db: Session = Depends(get_db_dependency)):
    _ = request.state.gettext
    form = await request.form()
    email = form.get("email")
    password = form.get("password")
    name = form.get("name")
    phone = form.get("phone")

    if not email or not password or not name:
        return templates.TemplateResponse("signup.html", {"request": request, "error": _("All fields are required.")})

    if crud.get_owner_by_email(db, email):
        return templates.TemplateResponse("signup.html", {"request": request, "error": _("Email already registered.")})

    hashed_password = get_password_hash(password)
    owner_create = schemas.OwnerCreate(email=email, password=password, name=name, phone=phone)
    db_owner = crud.create_owner(db, owner_create, hashed_password)

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": db_owner.email}, expires_delta=access_token_expires
    )
    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    response.set_cookie(key="access_token", value=f"Bearer {access_token}", httponly=True)
    return response

@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    response.delete_cookie(key="access_token")
    return response

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db_dependency), owner: models.Owner = Depends(get_current_owner)):
    _ = request.state.gettext
    services = crud.get_owner_services(db, owner.id)
    upcoming_bookings = crud.get_owner_upcoming_bookings(db, owner.id)
    analytics = crud.get_owner_analytics(db, owner.id)

    # Format prices for display
    for service in services:
        service.formatted_price = f"{service.price:.2f}"

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "owner": owner,
        "services": services,
        "upcoming_bookings": upcoming_bookings,
        "analytics": analytics,
        "subscription_status": owner.subscription_status
    })

@app.get("/dashboard/services/setup", response_class=HTMLResponse)
async def setup_service_page(request: Request, db: Session = Depends(get_db_dependency), owner: models.Owner = Depends(get_current_owner)):
    _ = request.state.gettext
    services = crud.get_owner_services(db, owner.id)
    return templates.TemplateResponse("service_setup.html", {"request": request, "owner": owner, "services": services, "error": None})

@app.post("/dashboard/services/setup", response_class=HTMLResponse)
async def create_service(request: Request, db: Session = Depends(get_db_dependency), owner: models.Owner = Depends(get_current_owner)):
    _ = request.state.gettext
    form = await request.form()
    name = form.get("name")
    description = form.get("description")
    duration = form.get("duration")
    price = form.get("price")

    if not name or not duration or not price:
        return templates.TemplateResponse("service_setup.html", {"request": request, "owner": owner, "services": crud.get_owner_services(db, owner.id), "error": _("Service name, duration, and price are required.")})

    try:
        service_create = schemas.ServiceCreate(name=name, description=description, duration=int(duration), price=float(price))
        crud.create_service(db=db, service=service_create, owner_id=owner.id)
        return RedirectResponse(url="/dashboard/services/setup", status_code=status.HTTP_303_SEE_OTHER)
    except ValueError:
        return templates.TemplateResponse("service_setup.html", {"request": request, "owner": owner, "services": crud.get_owner_services(db, owner.id), "error": _("Invalid duration or price format.")})

@app.get("/dashboard/profile", response_class=HTMLResponse)
async def owner_profile(request: Request, owner: models.Owner = Depends(get_current_owner)):
    _ = request.state.gettext
    return templates.TemplateResponse("profile.html", {"request": request, "owner": owner, "error": None, "success": None})

@app.post("/dashboard/profile", response_class=HTMLResponse)
async def update_owner_profile(request: Request, db: Session = Depends(get_db_dependency), owner: models.Owner = Depends(get_current_owner)):
    _ = request.state.gettext
    form = await request.form()
    name = form.get("name")
    email = form.get("email")
    phone = form.get("phone")

    update_data = {}
    if name: update_data["name"] = name
    if email: update_data["email"] = email
    if phone: update_data["phone"] = phone

    try:
        owner_update_schema = schemas.OwnerProfileUpdate(**update_data)
        updated_owner = crud.update_owner_profile(db, owner, owner_update_schema)
        return templates.TemplateResponse("profile.html", {"request": request, "owner": updated_owner, "error": None, "success": _("Profile updated successfully!")})
    except ValidationError as e:
        logger.error(f"Validation error updating owner profile: {e.errors()}")
        return templates.TemplateResponse("profile.html", {"request": request, "owner": owner, "error": _("Invalid input for profile fields."), "success": None})
    except Exception as e:
        logger.error(f"Error updating owner profile {owner.id}: {e}")
        raise HTTPException(status_code=500, detail=_("Failed to update profile."))

@app.get("/bookslot/{owner_name}", response_class=HTMLResponse)
async def public_booking_page(owner_name: str, request: Request, db: Session = Depends(get_db_dependency)):
    _ = request.state.gettext
    owner = db.query(models.Owner).filter(models.Owner.name == owner_name).first()
    if not owner:
        raise HTTPException(status_code=404, detail=_("Owner not found"))

    services = crud.get_owner_services(db, owner.id)
    
    # Format prices for display
    for service in services:
        service.formatted_price = f"{service.price:.2f}"

    return templates.TemplateResponse("booking_page.html", {"request": request, "owner": owner, "services": services, "error": None})

@app.post("/bookslot/{owner_name}", response_class=HTMLResponse)
async def submit_booking(owner_name: str, request: Request, db: Session = Depends(get_db_dependency)):
    _ = request.state.gettext
    owner = db.query(models.Owner).filter(models.Owner.name == owner_name).first()
    if not owner:
        raise HTTPException(status_code=404, detail=_("Owner not found"))

    form = await request.form()
    customer_name = form.get("customer_name")
    customer_email = form.get("customer_email")
    customer_phone = form.get("customer_phone")
    service_id = form.get("service_id")
    booking_date = form.get("booking_date")
    booking_time_str = form.get("booking_time")

    if not all([customer_name, customer_email, service_id, booking_date, booking_time_str]):
        services = crud.get_owner_services(db, owner.id)
        return templates.TemplateResponse("booking_page.html", {"request": request, "owner": owner, "services": services, "error": _("All fields are required.")})

    try:
        service = crud.get_service_by_id(db, int(service_id))
        if not service or service.owner_id != owner.id:
            services = crud.get_owner_services(db, owner.id)
            return templates.TemplateResponse("booking_page.html", {"request": request, "owner": owner, "services": services, "error": _("Invalid service selected.")})

        booking_datetime = datetime.strptime(f"{booking_date} {booking_time_str}", "%Y-%m-%d %H:%M")
        
        # Basic availability check (can be expanded)
        # Check if the slot is already booked or if it's in the past
        now = datetime.now()
        if booking_datetime < now:
            services = crud.get_owner_services(db, owner.id)
            return templates.TemplateResponse("booking_page.html", {"request": request, "owner": owner, "services": services, "error": _("Cannot book in the past.")})

        # Check for overlapping bookings for the same service (simplified)
        # This is a very basic check. A real system would need more sophisticated slot management.
        existing_bookings = db.query(models.Booking).filter(
            models.Booking.service_id == service.id,
            models.Booking.booking_time == booking_datetime
        ).first()

        if existing_bookings:
            services = crud.get_owner_services(db, owner.id)
            return templates.TemplateResponse("booking_page.html", {"request": request, "owner": owner, "services": services, "error": _("This time slot is already booked. Please choose another.")})

        booking_create = schemas.BookingCreate(
            customer_name=customer_name,
            customer_email=customer_email,
            customer_phone=customer_phone,
            service_id=int(service_id),
            booking_time=booking_datetime
        )
        db_booking = crud.create_booking(db=db, booking=booking_create, owner_id=owner.id)

        # Send notifications
        send_booking_confirmation_email(customer_email, customer_name, service.name, booking_datetime, owner.name, owner.email, owner.phone, request.state.locale)
        send_owner_notification_email(owner.email, customer_name, service.name, booking_datetime, customer_email, customer_phone, request.state.locale)
        if owner.phone:
            send_owner_notification_whatsapp(owner.phone, customer_name, service.name, booking_datetime, customer_email, customer_phone, request.state.locale)

        return templates.TemplateResponse("booking_confirmation.html", {
            "request": request,
            "customer_name": customer_name,
            "service_name": service.name,
            "booking_time": booking_datetime.strftime("%Y-%m-%d %H:%M"),
            "owner_name": owner.name,
            "owner_email": owner.email,
            "owner_phone": owner.phone
        })
    except ValueError:
        services = crud.get_owner_services(db, owner.id)
        return templates.TemplateResponse("booking_page.html", {"request": request, "owner": owner, "services": services, "error": _("Invalid date or time format.")})
    except Exception as e:
        logger.error(f"Error submitting booking for owner {owner.name}: {e}")
        services = crud.get_owner_services(db, owner.id)
        return templates.TemplateResponse("booking_page.html", {"request": request, "owner": owner, "services": services, "error": _("An unexpected error occurred. Please try again.")})

# Subscription management UI routes
@app.get("/dashboard/subscription", response_class=HTMLResponse)
async def subscription_management_page(request: Request, owner: models.Owner = Depends(get_current_owner)):
    _ = request.state.gettext
    return templates.TemplateResponse("subscription_management.html", {
        "request": request,
        "owner": owner,
        "stripe_public_key": settings.STRIPE_PUBLIC_KEY,
        "server_name": settings.SERVER_NAME
    })

@app.post("/create-checkout-session")
async def create_checkout_session(request: Request, db: Session = Depends(get_db_dependency), owner: models.Owner = Depends(get_current_owner)):
    _ = request.state.gettext
    if owner.subscription_status == "premium":
        raise HTTPException(status_code=400, detail=_("Owner is already subscribed to premium."))

    try:
        checkout_session = stripe.checkout.Session.create(
            line_items=[
                {
                    'price': settings.STRIPE_PRICE_ID,
                    'quantity': 1,
                },
            ],
            mode='subscription',
            success_url=f"{settings.SERVER_NAME}/dashboard/subscription?success=true",
            cancel_url=f"{settings.SERVER_NAME}/dashboard/subscription?canceled=true",
            customer=owner.stripe_customer_id if owner.stripe_customer_id else None, # Reuse customer if exists
            client_reference_id=str(owner.id), # Link to owner in Stripe
            metadata={"owner_id": str(owner.id)}
        )
        return RedirectResponse(checkout_session.url, status_code=303)
    except Exception as e:
        logger.error(f"Error creating checkout session for owner {owner.id}: {e}")
        raise HTTPException(status_code=500, detail=_("Failed to create checkout session."))

@app.post("/create-customer-portal-session")
async def create_customer_portal_session(request: Request, db: Session = Depends(get_db_dependency), owner: models.Owner = Depends(get_current_owner)):
    _ = request.state.gettext
    if not owner.stripe_customer_id:
        raise HTTPException(status_code=400, detail=_("No Stripe customer ID found for this owner."))

    try:
        portal_session = stripe.billing_portal.Session.create(
            customer=owner.stripe_customer_id,
            return_url=f"{settings.SERVER_NAME}/dashboard/subscription",
        )
        return RedirectResponse(portal_session.url, status_code=303)
    except Exception as e:
        logger.error(f"Error creating customer portal session for owner {owner.id}: {e}")
        raise HTTPException(status_code=500, detail=_("Failed to create customer portal session."))

@app.post("/stripe-webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db_dependency)):
    payload = await request.body()
    sig_header = request.headers.get('stripe-signature')

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError as e:
        logger.error(f"Invalid payload: {e}")
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError as e:
        logger.error(f"Invalid signature: {e}")
        raise HTTPException(status_code=400, detail="Invalid signature")

    # Handle the event
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        owner_id = session.get('client_reference_id')
        customer_id = session.get('customer')
        subscription_id = session.get('subscription')

        if owner_id and customer_id and subscription_id:
            owner = crud.get_owner(db, int(owner_id))
            if owner:
                crud.update_owner_subscription_status(db, owner, "premium", customer_id, subscription_id)
                logger.info(f"Owner {owner_id} subscription updated to premium.")
            else:
                logger.warning(f"Owner with ID {owner_id} not found for checkout.session.completed event.")
        else:
            logger.warning(f"Missing owner_id, customer_id, or subscription_id in checkout.session.completed event: {session}")

    elif event['type'] == 'customer.subscription.deleted':
        subscription = event['data']['object']
        customer_id = subscription.get('customer')
        
        owner = db.query(models.Owner).filter(models.Owner.stripe_customer_id == customer_id).first()
        if owner:
            crud.update_owner_subscription_status(db, owner, "cancelled", None, None)
            logger.info(f"Owner {owner.id} subscription status updated to cancelled.")
        else:
            logger.warning(f"Owner with Stripe customer ID {customer_id} not found for customer.subscription.deleted event.")
            
    elif event['type'] == 'customer.subscription.updated':
        subscription = event['data']['object']
        customer_id = subscription.get('customer')
        status = subscription.get('status')
        
        owner = db.query(models.Owner).filter(models.Owner.stripe_customer_id == customer_id).first()
        if owner:
            if owner.subscription_status != status:
                crud.update_owner_subscription_status(db, owner, status)
                logger.info(f"Owner {owner.id} subscription status updated to {status} by webhook.")
        else:
            logger.warning(f"Owner with Stripe customer ID {customer_id} not found for customer.subscription.updated event.")

    return {"status": "success"}

# Health check endpoint
@app.get("/health")
async def health_check():
    return {"status": "ok"}
