import os
from datetime import date, datetime, timedelta, time
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, Depends, HTTPException, status, Request, Form, APIRouter
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import func, extract

from jose import JWTError, jwt
from passlib.context import CryptContext

from . import models, schemas, crud, security, notifications, analytics, availability_utils, config
from .database import SessionLocal, engine, Base

# Internationalization
from starlette.middleware.sessions import SessionMiddleware
from starlette_babel import BabelMiddleware, gettext_babel as _
from starlette_babel import change_locale, get_locale

# Stripe
import stripe

# Create tables
Base.metadata.create_all(bind=engine)

app = FastAPI()

# Middleware for sessions and i18n
app.add_middleware(SessionMiddleware, secret_key=config.settings.SECRET_KEY)
app.add_middleware(BabelMiddleware, default_locale="en", babel_config={"load_path": ["./locales"]})

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Templates setup
templates = Jinja2Templates(directory="src/templates")
templates.env.globals['get_locale'] = get_locale
templates.env.globals['_'] = _

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

router = APIRouter()

# --- Auth Endpoints ---
@router.post("/token", response_model=schemas.Token)
async def login_for_access_token(db: Session = Depends(get_db), form_data: OAuth2PasswordRequestForm = Depends()):
    owner = security.authenticate_owner(db, form_data.username, form_data.password)
    if not owner:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=config.settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": owner.email}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@router.post("/signup", response_class=HTMLResponse)
async def signup_owner(
    request: Request,
    db: Session = Depends(get_db),
    email: str = Form(...),
    password: str = Form(...),
    full_name: str = Form(...),
    phone_number: Optional[str] = Form(None)
):
    db_owner = crud.get_owner_by_email(db, email=email)
    if db_owner:
        return templates.TemplateResponse(
            "signup.html",
            {"request": request, "error": _("Email already registered")},
            status_code=status.HTTP_400_BAD_REQUEST
        )
    owner = schemas.OwnerCreate(email=email, password=password, full_name=full_name, phone_number=phone_number)
    crud.create_owner(db=db, owner=owner)
    response = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    return response

@router.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request):
    return templates.TemplateResponse("signup.html", {"request": request})

@router.get("/logout")
async def logout(request: Request):
    response = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    response.delete_cookie("access_token")
    return response

# --- Language Toggle ---
@router.get("/lang/{locale_code}")
async def change_language(request: Request, locale_code: str):
    response = RedirectResponse(url=request.headers.get("referer", "/"), status_code=status.HTTP_302_FOUND)
    change_locale(locale_code, response)
    return response

# --- Dashboard Endpoints ---
@router.get("/dashboard", response_class=HTMLResponse)
async def read_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    current_owner: schemas.Owner = Depends(security.get_current_owner)
):
    owner_id = current_owner.id
    
    # Fetch upcoming individual bookings (not part of a recurring series)
    upcoming_bookings_db = db.query(models.Booking).filter(
        models.Booking.owner_id == owner_id,
        models.Booking.date >= date.today(),
        models.Booking.recurring_booking_id.is_(None)
    ).order_by(models.Booking.date, models.Booking.time).all()

    upcoming_bookings = []
    for booking in upcoming_bookings_db:
        service = db.query(models.Service).filter(models.Service.id == booking.service_id).first()
        if service:
            upcoming_bookings.append({
                "id": booking.id,
                "service_name": service.name,
                "customer_name": booking.customer_name,
                "date": booking.date,
                "time": booking.time,
                "customer_phone": booking.customer_phone
            })

    # Fetch recurring booking definitions
    recurring_booking_definitions = db.query(models.RecurringBooking).filter(
        models.RecurringBooking.owner_id == owner_id,
        (models.RecurringBooking.end_date >= date.today()) | (models.RecurringBooking.end_date.is_(None))
    ).order_by(models.RecurringBooking.start_date).all()

    recurring_bookings_display = []
    for rb_def in recurring_booking_definitions:
        service = db.query(models.Service).filter(models.Service.id == rb_def.service_id).first()
        if service:
            recurring_bookings_display.append({
                "id": rb_def.id,
                "service_name": service.name,
                "customer_name": rb_def.customer_name,
                "start_time": rb_def.start_time,
                "duration_minutes": rb_def.duration_minutes,
                "recurrence_type": rb_def.recurrence_type.value,
                "recurrence_value": rb_def.recurrence_value,
                "start_date": rb_def.start_date,
                "end_date": rb_def.end_date,
                "customer_phone": rb_def.customer_phone
            })

    # Analytics data
    monthly_bookings_data = analytics.get_monthly_bookings_data(db, owner_id)
    popular_services_data = analytics.get_popular_services_data(db, owner_id)

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "owner": current_owner,
            "upcoming_bookings": upcoming_bookings,
            "recurring_bookings": recurring_bookings_display,
            "monthly_bookings_data": monthly_bookings_data,
            "popular_services_data": popular_services_data,
            "current_date": date.today()
        }
    )

@router.get("/dashboard/profile", response_class=HTMLResponse)
async def get_owner_profile(
    request: Request,
    db: Session = Depends(get_db),
    current_owner: schemas.Owner = Depends(security.get_current_owner)
):
    return templates.TemplateResponse(
        "owner_profile.html",
        {"request": request, "owner": current_owner}
    )

@router.post("/dashboard/profile", response_class=HTMLResponse)
async def update_owner_profile(
    request: Request,
    db: Session = Depends(get_db),
    current_owner: schemas.Owner = Depends(security.get_current_owner),
    full_name: str = Form(...),
    phone_number: Optional[str] = Form(None)
):
    try:
        updated_owner = crud.update_owner(db, owner_id=current_owner.id, full_name=full_name, phone_number=phone_number)
        if not updated_owner:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Owner not found"))
        return templates.TemplateResponse(
            "owner_profile.html",
            {"request": request, "owner": updated_owner, "message": _("Profile updated successfully!")}
        )
    except Exception as e:
        return templates.TemplateResponse(
            "owner_profile.html",
            {"request": request, "owner": current_owner, "error": str(e)},
            status_code=status.HTTP_400_BAD_REQUEST
        )

# --- Service Endpoints ---
@router.get("/dashboard/services", response_class=HTMLResponse)
async def manage_services_page(
    request: Request,
    db: Session = Depends(get_db),
    current_owner: schemas.Owner = Depends(security.get_current_owner)
):
    services = crud.get_owner_services(db, owner_id=current_owner.id)
    return templates.TemplateResponse(
        "manage_services.html",
        {"request": request, "owner": current_owner, "services": services}
    )

@router.post("/dashboard/services", response_class=HTMLResponse)
async def add_service(
    request: Request,
    db: Session = Depends(get_db),
    current_owner: schemas.Owner = Depends(security.get_current_owner),
    name: str = Form(...),
    description: Optional[str] = Form(None),
    duration_minutes: int = Form(...),
    price: int = Form(...),
    currency: str = Form("USD")
):
    service_data = schemas.ServiceCreate(
        name=name,
        description=description,
        duration_minutes=duration_minutes,
        price=price,
        currency=currency
    )
    crud.create_owner_service(db, service=service_data, owner_id=current_owner.id)
    return RedirectResponse(url="/dashboard/services", status_code=status.HTTP_302_FOUND)

@router.post("/dashboard/services/{service_id}/delete", response_class=HTMLResponse)
async def delete_service(
    request: Request,
    service_id: int,
    db: Session = Depends(get_db),
    current_owner: schemas.Owner = Depends(security.get_current_owner)
):
    crud.delete_owner_service(db, service_id=service_id, owner_id=current_owner.id)
    return RedirectResponse(url="/dashboard/services", status_code=status.HTTP_302_FOUND)

# --- Availability Endpoints ---
@router.get("/dashboard/availability", response_class=HTMLResponse)
async def manage_availability_page(
    request: Request,
    db: Session = Depends(get_db),
    current_owner: schemas.Owner = Depends(security.get_current_owner)
):
    services = crud.get_owner_services(db, owner_id=current_owner.id)
    availabilities = crud.get_owner_availabilities(db, owner_id=current_owner.id)
    return templates.TemplateResponse(
        "manage_availability.html",
        {"request": request, "owner": current_owner, "services": services, "availabilities": availabilities}
    )

@router.post("/dashboard/availability", response_class=HTMLResponse)
async def add_availability(
    request: Request,
    db: Session = Depends(get_db),
    current_owner: schemas.Owner = Depends(security.get_current_owner),
    service_id: Optional[int] = Form(None),
    date_str: Optional[str] = Form(None),
    start_time_str: str = Form(...),
    end_time_str: str = Form(...),
    recurrence_type: Optional[models.RecurrenceType] = Form(None),
    recurrence_value: Optional[str] = Form(None),
    recurrence_start_date_str: Optional[str] = Form(None),
    recurrence_end_date_str: Optional[str] = Form(None)
):
    try:
        availability_data = schemas.AvailabilityCreate(
            service_id=service_id,
            date=date.fromisoformat(date_str) if date_str else None,
            start_time=time.fromisoformat(start_time_str),
            end_time=time.fromisoformat(end_time_str),
            recurrence_type=recurrence_type,
            recurrence_value=recurrence_value,
            recurrence_start_date=date.fromisoformat(recurrence_start_date_str) if recurrence_start_date_str else None,
            recurrence_end_date=date.fromisoformat(recurrence_end_date_str) if recurrence_end_date_str else None
        )
        crud.create_owner_availability(db, availability=availability_data, owner_id=current_owner.id)
        return RedirectResponse(url="/dashboard/availability", status_code=status.HTTP_302_FOUND)
    except Exception as e:
        services = crud.get_owner_services(db, owner_id=current_owner.id)
        availabilities = crud.get_owner_availabilities(db, owner_id=current_owner.id)
        return templates.TemplateResponse(
            "manage_availability.html",
            {"request": request, "owner": current_owner, "services": services, "availabilities": availabilities, "error": str(e)},
            status_code=status.HTTP_400_BAD_REQUEST
        )

@router.post("/dashboard/availability/{availability_id}/delete", response_class=HTMLResponse)
async def delete_availability(
    request: Request,
    availability_id: int,
    db: Session = Depends(get_db),
    current_owner: schemas.Owner = Depends(security.get_current_owner)
):
    crud.delete_owner_availability(db, availability_id=availability_id, owner_id=current_owner.id)
    return RedirectResponse(url="/dashboard/availability", status_code=status.HTTP_302_FOUND)

# --- Public Booking Page ---
@router.get("/book/{owner_name}", response_class=HTMLResponse)
async def booking_page(request: Request, owner_name: str, db: Session = Depends(get_db)):
    owner = db.query(models.Owner).filter(models.Owner.full_name == owner_name).first()
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Owner not found"))

    services = crud.get_owner_services(db, owner_id=owner.id)
    
    return templates.TemplateResponse(
        "booking_page.html",
        {"request": request, "owner": owner, "services": services, "current_date": date.today()}
    )

@router.post("/book/{owner_name}/submit", response_class=HTMLResponse)
async def submit_booking(
    request: Request,
    owner_name: str,
    db: Session = Depends(get_db),
    service_id: int = Form(...),
    customer_name: str = Form(...),
    customer_email: str = Form(...),
    customer_phone: Optional[str] = Form(None),
    booking_date_str: str = Form(...),
    booking_time_str: str = Form(...),
    is_recurring: bool = Form(False),
    recurrence_type: Optional[models.RecurrenceType] = Form(None),
    recurrence_value: Optional[str] = Form(None),
    recurrence_start_date_str: Optional[str] = Form(None),
    recurrence_end_date_str: Optional[str] = Form(None)
):
    owner = db.query(models.Owner).filter(models.Owner.full_name == owner_name).first()
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Owner not found"))

    service = db.query(models.Service).filter(models.Service.id == service_id, models.Service.owner_id == owner.id).first()
    if not service:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Service not found for this owner"))

    try:
        booking_date = date.fromisoformat(booking_date_str)
        booking_time = time.fromisoformat(booking_time_str)
        
        available_slots = availability_utils.get_available_slots_for_day(
            db, owner.id, service.id, booking_date, service.duration_minutes
        )
        if booking_time not in available_slots:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_("Selected slot is not available or already booked."))

        if is_recurring:
            recurrence_start_date = date.fromisoformat(recurrence_start_date_str) if recurrence_start_date_str else booking_date
            recurrence_end_date = date.fromisoformat(recurrence_end_date_str) if recurrence_end_date_str else None

            if not recurrence_type:
                 raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_("Recurrence type is required for recurring bookings."))

            recurring_booking_data = schemas.RecurringBookingCreate(
                service_id=service_id,
                customer_name=customer_name,
                customer_email=customer_email,
                customer_phone=customer_phone,
                start_time=booking_time,
                duration_minutes=service.duration_minutes,
                recurrence_type=recurrence_type,
                recurrence_value=recurrence_value,
                start_date=recurrence_start_date,
                end_date=recurrence_end_date
            )
            recurring_booking = crud.create_recurring_booking(db, recurring_booking_data, owner.id)
            
            booking_data = schemas.BookingCreate(
                service_id=service_id,
                customer_name=customer_name,
                customer_email=customer_email,
                customer_phone=customer_phone,
                date=booking_date,
                time=booking_time,
                recurring_booking_id=recurring_booking.id
            )
            booking = crud.create_booking(db, booking_data, owner.id)
            
        else:
            booking_data = schemas.BookingCreate(
                service_id=service_id,
                customer_name=customer_name,
                customer_email=customer_email,
                customer_phone=customer_phone,
                date=booking_date,
                time=booking_time
            )
            booking = crud.create_booking(db, booking_data, owner.id)

        notifications.send_booking_confirmation_email(
            customer_email, owner.email, owner.full_name, service.name, booking_date, booking_time, service.duration_minutes
        )
        if owner.phone_number:
            notifications.send_owner_sms_notification(
                owner.phone_number, owner.full_name, service.name, booking_date, booking_time, customer_name, customer_phone
            )
        
        return templates.TemplateResponse(
            "booking_confirmation.html",
            {"request": request, "owner": owner, "booking": booking, "service": service, "is_recurring": is_recurring}
        )

    except HTTPException as e:
        services = crud.get_owner_services(db, owner_id=owner.id)
        return templates.TemplateResponse(
            "booking_page.html",
            {"request": request, "owner": owner, "services": services, "error": e.detail, "current_date": date.today()},
            status_code=e.status_code
        )
    except Exception as e:
        services = crud.get_owner_services(db, owner_id=owner.id)
        return templates.TemplateResponse(
            "booking_page.html",
            {"request": request, "owner": owner, "services": services, "error": _("An unexpected error occurred: ") + str(e), "current_date": date.today()},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

# --- Analytics API Endpoint ---
@router.get("/api/analytics/monthly_bookings", response_model=List[Dict[str, Any]])
async def get_monthly_bookings_api(
    db: Session = Depends(get_db),
    current_owner: schemas.Owner = Depends(security.get_current_owner)
):
    return analytics.get_monthly_bookings_data(db, current_owner.id)

@router.get("/api/analytics/popular_services", response_model=List[Dict[str, Any]])
async def get_popular_services_api(
    db: Session = Depends(get_db),
    current_owner: schemas.Owner = Depends(security.get_current_owner)
):
    return analytics.get_popular_services_data(db, current_owner.id)


# --- Subscription Management ---
stripe.api_key = config.settings.STRIPE_API_KEY

@router.get("/dashboard/subscription", response_class=HTMLResponse)
async def manage_subscription_page(
    request: Request,
    db: Session = Depends(get_db),
    current_owner: schemas.Owner = Depends(security.get_current_owner)
):
    subscription_status = current_owner.subscription_status
    upcoming_invoice = None
    if current_owner.stripe_customer_id:
        try:
            customer = stripe.Customer.retrieve(current_owner.stripe_customer_id)
            subscriptions = stripe.Subscription.list(customer=current_owner.stripe_customer_id, status='active', limit=1)
            if subscriptions.data:
                subscription = subscriptions.data[0]
                subscription_status = subscription.status
                upcoming_invoice = stripe.Invoice.upcoming(customer=current_owner.stripe_customer_id)
        except stripe.error.StripeError as e:
            print(f"Stripe error fetching subscription: {e}")
            pass

    return templates.TemplateResponse(
        "subscription_management.html",
        {
            "request": request,
            "owner": current_owner,
            "subscription_status": subscription_status,
            "upcoming_invoice": upcoming_invoice
        }
    )

@router.post("/create-checkout-session")
async def create_checkout_session(
    current_owner: schemas.Owner = Depends(security.get_current_owner)
):
    try:
        checkout_session = stripe.checkout.Session.create(
            line_items=[
                {
                    'price': config.settings.STRIPE_PREMIUM_PRICE_ID,
                    'quantity': 1,
                },
            ],
            mode='subscription',
            success_url='http://localhost:8000/dashboard/subscription?success=true',
            cancel_url='http://localhost:8000/dashboard/subscription?canceled=true',
            customer=current_owner.stripe_customer_id if current_owner.stripe_customer_id else None,
            client_reference_id=str(current_owner.id)
        )
        return RedirectResponse(checkout_session.url, status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.post("/stripe-webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get('stripe-signature')
    event = None

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, config.settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except stripe.error.SignatureVerificationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        owner_id = session.get('client_reference_id')
        customer_id = session.get('customer')

        if owner_id and customer_id:
            owner = crud.get_owner(db, owner_id=int(owner_id))
            if owner:
                owner.stripe_customer_id = customer_id
                owner.subscription_status = "active"
                db.add(owner)
                db.commit()
                db.refresh(owner)
                print(f"Owner {owner_id} updated with Stripe customer ID {customer_id} and subscription status 'active'")

    elif event['type'] == 'customer.subscription.updated' or event['type'] == 'customer.subscription.deleted':
        subscription = event['data']['object']
        customer_id = subscription['customer']
        owner = crud.get_owner_by_stripe_customer_id(db, stripe_customer_id=customer_id)
        if owner:
            owner.subscription_status = subscription['status']
            db.add(owner)
            db.commit()
            db.refresh(owner)
            print(f"Owner {owner.id} subscription status updated to {subscription['status']}")

    return {"status": "success"}

# --- Health Check ---
@router.get("/health")
async def health_check():
    return {"status": "ok"}

app.include_router(router)
