import logging
from fastapi import FastAPI, Depends, HTTPException, status, Request, Response, Form
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import timedelta, date, datetime, time
from typing import List, Optional, Dict, Any
from babel.dates import format_date, format_time
import calendar
import json
from gettext import gettext as _ # For internationalization in Python code

from . import models, schemas, security, database, notifications, analytics, availability_utils
from .database import engine, get_db
from .config import settings
from .i18n import get_locale, gettext_filter, format_currency_filter, format_date_filter, format_time_filter, get_language_from_request
from .security import get_current_owner, get_current_customer, create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES, get_password_hash, verify_password, reusable_oauth2
from .stripe_utils import create_checkout_session, handle_webhook_event, get_subscription_details
from .models import RecurrenceType # Import RecurrenceType

models.Base.metadata.create_all(bind=engine)

app = FastAPI()

# Logging setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Templates setup
templates = Jinja2Templates(directory="templates")

# Add i18n filters to Jinja2 environment
templates.env.filters['gettext'] = gettext_filter
templates.env.filters['format_currency'] = format_currency_filter
templates.env.filters['format_date'] = format_date_filter
templates.env.filters['format_time'] = format_time_filter

@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.post("/token", response_model=schemas.Token)
async def login_for_access_token(db: Session = Depends(get_db), form_data: OAuth2PasswordRequestForm = Depends()):
    owner = security.authenticate_owner(db, form_data.username, form_data.password)
    if not owner:
        logger.warning(f"Owner login failed for username: {form_data.username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_("Incorrect username or password"),
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": owner.email, "user_type": "owner"}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/customer-token", response_model=schemas.Token)
async def customer_login_for_access_token(db: Session = Depends(get_db), form_data: OAuth2PasswordRequestForm = Depends()):
    customer = security.authenticate_customer(db, form_data.username, form_data.password)
    if not customer:
        logger.warning(f"Customer login failed for username: {form_data.username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_("Incorrect email or password"),
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": customer.email, "user_type": "customer"}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/register", response_class=RedirectResponse)
async def register_owner(request: Request, db: Session = Depends(get_db), email: str = Form(...), password: str = Form(...), name: str = Form(...), username: str = Form(...)):
    if db.query(models.Owner).filter(models.Owner.email == email).first():
        return templates.TemplateResponse("register.html", {"request": request, "error_message": _("Email already registered"), "locale": get_locale()}, status_code=status.HTTP_400_BAD_REQUEST)
    if db.query(models.Owner).filter(models.Owner.username == username).first():
        return templates.TemplateResponse("register.html", {"request": request, "error_message": _("Username already taken"), "locale": get_locale()}, status_code=status.HTTP_400_BAD_REQUEST)

    hashed_password = security.get_password_hash(password)
    owner = models.Owner(email=email, hashed_password=hashed_password, name=name, username=username)
    db.add(owner)
    db.commit()
    db.refresh(owner)
    return RedirectResponse(url="/login?message=registration_success", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, message: Optional[str] = None):
    context = {"request": request, "locale": get_locale(), "message": message}
    return templates.TemplateResponse("login.html", context)

@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request, "locale": get_locale()})

@app.get("/dashboard", response_class=HTMLResponse)
async def owner_dashboard(request: Request, db: Session = Depends(get_db), current_owner: models.Owner = Depends(get_current_owner), message: Optional[str] = None, error_message: Optional[str] = None, active_tab: str = "bookings"):
    bookings_data = db.query(models.Booking).filter(models.Booking.owner_id == current_owner.id).order_by(models.Booking.date, models.Booking.time).all()
    services = db.query(models.Service).filter(models.Service.owner_id == current_owner.id).all()
    availabilities = db.query(models.Availability).filter(models.Availability.owner_id == current_owner.id).order_by(models.Availability.date, models.Availability.start_time).all()

    # Analytics data
    monthly_bookings = analytics.get_monthly_bookings_data(db, current_owner.id)
    popular_services = analytics.get_popular_services_data(db, current_owner.id)

    # Subscription details
    subscription = get_subscription_details(current_owner.stripe_customer_id) if current_owner.stripe_customer_id else None
    
    context = {
        "request": request,
        "owner": current_owner,
        "bookings": bookings_data,
        "services": services,
        "availabilities": availabilities,
        "message": message,
        "error_message": error_message,
        "locale": get_locale(),
        "active_tab": active_tab,
        "monthly_bookings": monthly_bookings,
        "popular_services": popular_services,
        "subscription": subscription
    }
    return templates.TemplateResponse("dashboard.html", context)

@app.post("/dashboard/profile", response_class=HTMLResponse)
async def update_owner_profile(
    request: Request,
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(get_current_owner),
    name: str = Form(...),
    email: str = Form(...),
    phone: Optional[str] = Form(None),
    currency: Optional[str] = Form(None),
    username: str = Form(...),
    company_name: Optional[str] = Form(None)
):
    try:
        # Check if new username is already taken by another owner
        if username != current_owner.username:
            existing_owner = db.query(models.Owner).filter(models.Owner.username == username).first()
            if existing_owner:
                logger.warning(f"Attempt to update owner profile with duplicate username: {username} by owner_id: {current_owner.id}")
                return templates.TemplateResponse(
                    "dashboard.html",
                    {"request": request, "owner": current_owner, "error_message": _("Username already taken."), "locale": get_locale(), "active_tab": "profile"},
                    status_code=status.HTTP_400_BAD_REQUEST
                )
        # Check if new email is already taken by another owner
        if email != current_owner.email:
            existing_owner = db.query(models.Owner).filter(models.Owner.email == email).first()
            if existing_owner:
                logger.warning(f"Attempt to update owner profile with duplicate email: {email} by owner_id: {current_owner.id}")
                return templates.TemplateResponse(
                    "dashboard.html",
                    {"request": request, "owner": current_owner, "error_message": _("Email already taken."), "locale": get_locale(), "active_tab": "profile"},
                    status_code=status.HTTP_400_BAD_REQUEST
                )

        current_owner.name = name
        current_owner.email = email
        current_owner.phone = phone
        current_owner.currency = currency
        current_owner.username = username
        current_owner.company_name = company_name
        
        db.add(current_owner)
        db.commit()
        db.refresh(current_owner)
        
        return RedirectResponse(url="/dashboard?tab=profile&message=profile_updated", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        logger.error(f"Error updating owner profile for owner_id: {current_owner.id}, error: {e}")
        return templates.TemplateResponse(
            "dashboard.html",
            {"request": request, "owner": current_owner, "error_message": _("Failed to update profile."), "locale": get_locale(), "active_tab": "profile"},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@app.post("/dashboard/services", response_class=RedirectResponse)
async def add_service(db: Session = Depends(get_db), current_owner: models.Owner = Depends(get_current_owner), name: str = Form(...), description: str = Form(...), duration_minutes: int = Form(...), price: float = Form(...)):
    service = models.Service(owner_id=current_owner.id, name=name, description=description, duration_minutes=duration_minutes, price=price)
    db.add(service)
    db.commit()
    db.refresh(service)
    return RedirectResponse(url="/dashboard?tab=services&message=service_added", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/dashboard/services/edit/{service_id}", response_class=RedirectResponse)
async def edit_service(service_id: int, db: Session = Depends(get_db), current_owner: models.Owner = Depends(get_current_owner), name: str = Form(...), description: str = Form(...), duration_minutes: int = Form(...), price: float = Form(...)):
    service = db.query(models.Service).filter(models.Service.id == service_id, models.Service.owner_id == current_owner.id).first()
    if not service:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Service not found"))
    service.name = name
    service.description = description
    service.duration_minutes = duration_minutes
    service.price = price
    db.add(service)
    db.commit()
    db.refresh(service)
    return RedirectResponse(url="/dashboard?tab=services&message=service_updated", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/dashboard/services/delete/{service_id}", response_class=RedirectResponse)
async def delete_service(service_id: int, db: Session = Depends(get_db), current_owner: models.Owner = Depends(get_current_owner)):
    service = db.query(models.Service).filter(models.Service.id == service_id, models.Service.owner_id == current_owner.id).first()
    if not service:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Service not found"))
    db.delete(service)
    db.commit()
    return RedirectResponse(url="/dashboard?tab=services&message=service_deleted", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/dashboard/availabilities", response_class=RedirectResponse)
async def add_availability(db: Session = Depends(get_db), current_owner: models.Owner = Depends(get_current_owner), start_time: time = Form(...), end_time: time = Form(...), date: Optional[date] = Form(None), service_id: Optional[int] = Form(None), recurrence_type: Optional[RecurrenceType] = Form(None), recurrence_value: Optional[str] = Form(None), recurrence_start_date: Optional[date] = Form(None), recurrence_end_date: Optional[date] = Form(None)):
    availability = models.Availability(
        owner_id=current_owner.id, start_time=start_time, end_time=end_time, date=date,
        service_id=service_id, recurrence_type=recurrence_type, recurrence_value=recurrence_value,
        recurrence_start_date=recurrence_start_date, recurrence_end_date=recurrence_end_date
    )
    db.add(availability)
    db.commit()
    db.refresh(availability)
    return RedirectResponse(url="/dashboard?tab=availability&message=availability_added", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/dashboard/availabilities/delete/{availability_id}", response_class=RedirectResponse)
async def delete_availability(availability_id: int, db: Session = Depends(get_db), current_owner: models.Owner = Depends(get_current_owner)):
    availability = db.query(models.Availability).filter(models.Availability.id == availability_id, models.Availability.owner_id == current_owner.id).first()
    if not availability:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Availability not found"))
    db.delete(availability)
    db.commit()
    return RedirectResponse(url="/dashboard?tab=availability&message=availability_deleted", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/{owner_username}", response_class=HTMLResponse)
async def public_booking_page(request: Request, owner_username: str, db: Session = Depends(get_db), lang: Optional[str] = None):
    owner = db.query(models.Owner).filter(models.Owner.username == owner_username).first()
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Owner not found"))
    
    # Get services for the owner
    services = db.query(models.Service).filter(models.Service.owner_id == owner.id).all()
    
    # Determine selected service or default to first one
    selected_service_id = request.query_params.get("service_id", services[0].id if services else None)
    selected_service = next((s for s in services if s.id == int(selected_service_id)), services[0] if services else None)

    # Get today's date for calendar initialization
    today = date.today()

    context = {
        "request": request,
        "owner": owner,
        "services": services,
        "selected_service": selected_service,
        "today": today,
        "locale": get_locale(lang), # Pass lang from query param
        "lang_code": get_language_from_request(request) # For language toggle
    }
    return templates.TemplateResponse("booking_page.html", context)

@app.get("/api/slots/{owner_username}/{service_id}/{target_date}", response_model=List[time])
async def get_available_slots(
    owner_username: str,
    service_id: int,
    target_date: date,
    db: Session = Depends(get_db)
):
    owner = db.query(models.Owner).filter(models.Owner.username == owner_username).first()
    service = db.query(models.Service).filter(models.Service.id == service_id, models.Service.owner_id == owner.id).first()

    if not owner or not service:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Owner or Service not found"))

    return availability_utils.get_available_slots_for_day(db, owner.id, service.id, target_date, service.duration_minutes)

@app.post("/bookings/{owner_username}/{service_id}", response_class=HTMLResponse)
async def create_booking_public(
    request: Request,
    owner_username: str,
    service_id: int,
    db: Session = Depends(get_db),
    customer_name: str = Form(...),
    customer_email: str = Form(...),
    customer_phone: Optional[str] = Form(None),
    booking_date: date = Form(...),
    booking_time: time = Form(...),
    is_recurring: bool = Form(False),
    recurrence_type: Optional[RecurrenceType] = Form(None),
    recurrence_value: Optional[str] = Form(None),
    recurrence_end_date: Optional[date] = Form(None)
):
    owner = db.query(models.Owner).filter(models.Owner.username == owner_username).first()
    service = db.query(models.Service).filter(models.Service.id == service_id, models.Service.owner_id == owner.id).first()

    if not owner or not service:
        logger.error(f"Booking attempt for non-existent owner/service: owner_username={owner_username}, service_id={service_id}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Owner or Service not found"))

    # Validate input data
    try:
        booking_data = schemas.BookingCreate(
            owner_id=owner.id,
            service_id=service.id,
            customer_name=customer_name,
            customer_email=customer_email,
            customer_phone=customer_phone,
            date=booking_date,
            time=booking_time,
            is_recurring=is_recurring,
            recurrence_type=recurrence_type,
            recurrence_value=recurrence_value,
            recurrence_end_date=recurrence_end_date
        )
    except Exception as e:
        logger.warning(f"Invalid booking data submitted: {e} from IP: {request.client.host}")
        return templates.TemplateResponse(
            "booking_page.html",
            {"request": request, "owner": owner, "service": service, "error_message": _("Invalid booking data provided."), "locale": get_locale(), "lang_code": get_language_from_request(request)},
            status_code=status.HTTP_400_BAD_REQUEST
        )
    
    # Check for existing customer or create new one
    customer = db.query(models.Customer).filter(models.Customer.email == customer_email).first()
    if not customer:
        customer = models.Customer(name=customer_name, email=customer_email, phone=customer_phone)
        db.add(customer)
        db.commit()
        db.refresh(customer)
    
    # Check availability
    available_slots = availability_utils.get_available_slots_for_day(
        db, owner.id, service.id, booking_date, service.duration_minutes
    )

    if booking_time not in available_slots:
        logger.warning(f"Attempt to book unavailable slot: owner_id={owner.id}, service_id={service.id}, date={booking_date}, time={booking_time}")
        return templates.TemplateResponse(
            "booking_page.html",
            {"request": request, "owner": owner, "service": service, "error_message": _("Selected time slot is not available."), "locale": get_locale(), "lang_code": get_language_from_request(request)},
            status_code=status.HTTP_400_BAD_REQUEST
        )

    try:
        if is_recurring:
            # Handle recurring bookings
            if not recurrence_type or not recurrence_value or not recurrence_end_date:
                 raise ValueError(_("Recurring booking requires recurrence type, value, and end date."))

            # Create the initial booking
            booking = models.Booking(
                owner_id=owner.id, service_id=service.id, customer_id=customer.id,
                customer_name=customer_name, customer_email=customer_email, customer_phone=customer_phone,
                date=booking_date, time=booking_time, is_recurring=True,
                recurrence_type=recurrence_type,
                recurrence_value=recurrence_value,
                recurrence_end_date=recurrence_end_date
            )
            db.add(booking)
            db.commit()
            db.refresh(booking)

            # For simplicity, we'll notify only the initial booking. 
            # A more advanced system would notify for each occurrence or send a summary.
            notifications.send_booking_confirmation_email(owner, service, booking, customer_email)
            notifications.send_new_booking_notification_to_owner(owner, service, booking)
            if customer_phone:
                notifications.send_booking_confirmation_sms(owner, service, booking, customer_phone)

            return templates.TemplateResponse("booking_confirmation.html", {"request": request, "owner": owner, "service": service, "booking": booking, "locale": get_locale(), "lang_code": get_language_from_request(request), "is_recurring": True})

        else:
            # Handle one-off bookings
            booking = models.Booking(
                owner_id=owner.id, service_id=service.id, customer_id=customer.id,
                customer_name=customer_name, customer_email=customer_email, customer_phone=customer_phone,
                date=booking_date, time=booking_time, is_recurring=False
            )
            db.add(booking)
            db.commit()
            db.refresh(booking)

            notifications.send_booking_confirmation_email(owner, service, booking, customer_email)
            notifications.send_new_booking_notification_to_owner(owner, service, booking)
            if customer_phone:
                notifications.send_booking_confirmation_sms(owner, service, booking, customer_phone)

            return templates.TemplateResponse("booking_confirmation.html", {"request": request, "owner": owner, "service": service, "booking": booking, "locale": get_locale(), "lang_code": get_language_from_request(request), "is_recurring": False})

    except Exception as e:
        logger.error(f"Error creating booking for owner_id={owner.id}, service_id={service.id}: {e}")
        return templates.TemplateResponse(
            "booking_page.html",
            {"request": request, "owner": owner, "service": service, "error_message": _("An error occurred during booking. Please try again."), "locale": get_locale(), "lang_code": get_language_from_request(request)},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@app.get("/booking-confirmation", response_class=HTMLResponse)
async def booking_confirmation_page(request: Request):
    # This page is typically redirected to after a successful booking
    # and would display details passed via query parameters or session.
    # For simplicity, just render a generic confirmation or redirect back to main booking page.
    return templates.TemplateResponse("booking_confirmation.html", {"request": request, "locale": get_locale(), "lang_code": get_language_from_request(request)})

# Stripe Webhook endpoint
@app.post("/stripe-webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get('stripe-signature')

    try:
        event = handle_webhook_event(payload, sig_header, settings.STRIPE_WEBHOOK_SECRET)
    except ValueError as e:
        # Invalid payload
        logger.error(f"Invalid Stripe payload: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # Invalid signature
        logger.error(f"Invalid Stripe signature: {e}")
        raise HTTPException(status_code=400, detail=str(e))

    # Handle the event
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        customer_email = session.get('customer_details', {}).get('email')
        owner = db.query(models.Owner).filter(models.Owner.email == customer_email).first()
        if owner:
            owner.is_premium = True
            owner.stripe_customer_id = session.get('customer') # Store Stripe Customer ID
            owner.stripe_subscription_id = session.get('subscription') # Store Stripe Subscription ID
            db.add(owner)
            db.commit()
            db.refresh(owner)
            logger.info(f"Owner {owner.email} upgraded to premium. Stripe Customer ID: {owner.stripe_customer_id}")
        else:
            logger.warning(f"Checkout session completed for unknown owner email: {customer_email}")
    elif event['type'] == 'customer.subscription.deleted':
        subscription = event['data']['object']
        stripe_customer_id = subscription.get('customer')
        owner = db.query(models.Owner).filter(models.Owner.stripe_customer_id == stripe_customer_id).first()
        if owner:
            owner.is_premium = False
            owner.stripe_subscription_id = None
            db.add(owner)
            db.commit()
            db.refresh(owner)
            logger.info(f"Owner {owner.email} subscription cancelled.")
        else:
            logger.warning(f"Subscription deleted for unknown Stripe customer ID: {stripe_customer_id}")
    
    # ... handle other event types as needed

    return Response(status_code=200)

@app.post("/create-checkout-session", response_model=schemas.StripeCheckoutSession)
async def create_stripe_checkout_session(db: Session = Depends(get_db), current_owner: models.Owner = Depends(get_current_owner)):
    try:
        session_id, session_url = create_checkout_session(current_owner.email, current_owner.id)
        return schemas.StripeCheckoutSession(session_id=session_id, session_url=session_url)
    except Exception as e:
        logger.error(f"Error creating Stripe checkout session for owner_id {current_owner.id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=_("Failed to create checkout session."))

@app.get("/dashboard/subscription", response_class=HTMLResponse)
async def manage_subscription(request: Request, db: Session = Depends(get_db), current_owner: models.Owner = Depends(get_current_owner)):
    subscription_details = None
    if current_owner.stripe_customer_id:
        subscription_details = get_subscription_details(current_owner.stripe_customer_id)
    
    context = {
        "request": request,
        "owner": current_owner,
        "locale": get_locale(),
        "active_tab": "subscription",
        "subscription": subscription_details
    }
    return templates.TemplateResponse("dashboard.html", context)

# Admin panel routes (basic examples)
# Assuming an admin role check would be applied, e.g., via a custom dependency
async def get_current_admin_owner(current_owner: models.Owner = Depends(get_current_owner)):
    # This is a placeholder for actual admin role checking
    # In a real app, you'd check if current_owner has an 'is_admin' flag or belongs to an 'admin' group
    if not current_owner.is_admin: # Assuming an 'is_admin' field on Owner model
        logger.warning(f"Unauthorized admin access attempt by owner_id: {current_owner.id}")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_("Not authorized to access admin panel"))
    return current_owner

@app.get("/admin/owners", response_class=HTMLResponse)
async def admin_list_owners(request: Request, db: Session = Depends(get_db), admin_owner: models.Owner = Depends(get_current_admin_owner)):
    owners = db.query(models.Owner).all()
    context = {"request": request, "owners": owners, "locale": get_locale(), "active_tab": "owners"}
    return templates.TemplateResponse("admin_dashboard.html", context)

@app.get("/admin/owners/{owner_id}", response_class=HTMLResponse)
async def admin_view_owner(request: Request, owner_id: int, db: Session = Depends(get_db), admin_owner: models.Owner = Depends(get_current_admin_owner)):
    owner = db.query(models.Owner).filter(models.Owner.id == owner_id).first()
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Owner not found"))
    services = db.query(models.Service).filter(models.Service.owner_id == owner_id).all()
    bookings = db.query(models.Booking).filter(models.Booking.owner_id == owner_id).all()
    context = {"request": request, "owner": owner, "services": services, "bookings": bookings, "locale": get_locale()}
    return templates.TemplateResponse("admin_owner_detail.html", context)

# Customer routes
@app.post("/customer/register", response_model=schemas.Customer)
async def customer_register(customer_in: schemas.CustomerCreate, db: Session = Depends(get_db)):
    existing_customer = db.query(models.Customer).filter(models.Customer.email == customer_in.email).first()
    if existing_customer:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_("Email already registered"))
    hashed_password = security.get_password_hash(customer_in.password)
    customer = models.Customer(**customer_in.model_dump(exclude_unset=True, exclude={"password"}), hashed_password=hashed_password)
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer

@app.get("/customer/profile", response_model=schemas.Customer)
async def customer_profile(current_customer: models.Customer = Depends(get_current_customer)):
    return current_customer

@app.put("/customer/profile", response_model=schemas.Customer)
async def update_customer_profile(customer_update: schemas.CustomerUpdate, db: Session = Depends(get_db), current_customer: models.Customer = Depends(get_current_customer)):
    for field, value in customer_update.model_dump(exclude_unset=True).items():
        if field == "password" and value:
            current_customer.hashed_password = security.get_password_hash(value)
        else:
            setattr(current_customer, field, value)
    db.add(current_customer)
    db.commit()
    db.refresh(current_customer)
    return current_customer

@app.delete("/api/customer/bookings/{booking_id}")
async def cancel_customer_booking(booking_id: int, db: Session = Depends(get_db), current_customer: models.Customer = Depends(get_current_customer)):
    booking = db.query(models.Booking).filter(models.Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Booking not found"))
    if booking.customer_id != current_customer.id:
        logger.warning(f"Customer {current_customer.id} attempted to cancel booking {booking_id} belonging to customer {booking.customer_id}")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_("Not authorized to cancel this booking"))
    db.delete(booking)
    db.commit()
    return {"message": _("Booking cancelled successfully")} # Changed to return dict for consistency with previous responses

# Review and Rating System Endpoints
@app.post("/api/services/{service_id}/reviews", response_model=schemas.Review)
async def submit_review(
    service_id: int,
    review_create: schemas.ReviewCreate,
    db: Session = Depends(get_db),
    current_customer: models.Customer = Depends(get_current_customer) # Only logged-in customers can review
):
    service = db.query(models.Service).filter(models.Service.id == service_id).first()
    if not service:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Service not found"))
    
    # Check if the customer has a booking for this service to be eligible to review
    # This is a business logic decision. For simplicity, we'll allow any logged-in customer for now.
    # In a real app: check if customer has completed a booking for this service.
    
    review = models.Review(
        service_id=service_id,
        customer_id=current_customer.id,
        rating=review_create.rating,
        comment=review_create.comment
    )
    db.add(review)
    db.commit()
    db.refresh(review)
    return review

@app.get("/api/services/{service_id}/reviews", response_model=List[schemas.Review])
async def get_service_reviews(service_id: int, db: Session = Depends(get_db)):
    reviews = db.query(models.Review).filter(models.Review.service_id == service_id).all()
    return reviews

@app.get("/api/owner/{owner_id}/reviews", response_model=List[schemas.Review])
async def get_owner_reviews(owner_id: int, db: Session = Depends(get_db)):
    # Get reviews for all services belonging to this owner
    reviews = db.query(models.Review).join(models.Service).filter(models.Service.owner_id == owner_id).all()
    return reviews

# Language toggle endpoint
@app.post("/set-language/{lang_code}", response_class=RedirectResponse)
async def set_language(request: Request, lang_code: str):
    response = RedirectResponse(url=request.headers.get("referer", "/"), status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(key="lang", value=lang_code, httponly=True, max_age=30*24*60*60) # 30 days
    return response
