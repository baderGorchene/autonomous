from fastapi import FastAPI, Depends, HTTPException, status, Request, Form, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.encoders import jsonable_encoder
from typing import List, Optional
from datetime import datetime, time, timedelta
import pytz
import stripe
import json
import gettext
from gettext import gettext as _ # Alias for direct use of gettext
from babel.dates import format_date, format_datetime, format_time
from babel.numbers import format_currency

from . import crud, models, schemas, security, notifications
from .database import SessionLocal, engine, get_db
from .config import settings

models.Base.metadata.create_all(bind=engine)

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Internationalization setup
locales_dir = settings.LOCALES_DIR
LANGUAGES = {"en": "English", "ar": "العربية", "fr": "Français"}

def get_locale(request: Request):
    # Try to get language from cookie
    lang = request.cookies.get("lang")
    if lang and lang in LANGUAGES:
        return lang
    # Fallback to Accept-Language header (simplified, might need more robust parsing)
    accept_language = request.headers.get("Accept-Language", settings.DEFAULT_LOCALE)
    for lang_code in accept_language.split(','):
        lang_code = lang_code.split(';')[0].strip().lower()
        if lang_code in LANGUAGES:
            return lang_code
    return settings.DEFAULT_LOCALE

def get_translator(request: Request):
    lang = get_locale(request)
    try:
        # Load translation for the determined language
        t = gettext.translation('messages', locales_dir, languages=[lang], fallback=True)
        t.install()
        return t.gettext
    except Exception as e:
        print(f"Error loading translation for {lang}: {e}")
        return gettext.gettext # Fallback to default gettext

@app.middleware("http")
async def add_i18n_context(request: Request, call_next):
    _ = get_translator(request)
    request.state.gettext = _

    # Add locale and formatters to request state for templates
    request.state.locale = get_locale(request)
    request.state.format_datetime = lambda dt, format='medium', locale=request.state.locale: format_datetime(dt, format=format, locale=locale)
    request.state.format_date = lambda d, format='medium', locale=request.state.locale: format_date(d, format=format, locale=locale)
    request.state.format_time = lambda t, format='medium', locale=request.state.locale: format_time(t, format=format, locale=locale)
    request.state.format_currency = lambda amount, currency, locale=request.state.locale: format_currency(amount, currency, locale=locale)

    response = await call_next(request)
    return response

@app.get("/health", response_class=HTMLResponse)
async def health_check():
    return "OK"

@app.get("/set-language/{lang}")
async def set_language(lang: str, response: Response):
    if lang in LANGUAGES:
        response.set_cookie(key="lang", value=lang, httponly=True, max_age=3600*24*30) # 30 days
    return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND) # Redirect to home or referrer


@app.post("/token", response_model=schemas.Token)
async def login_for_access_token(request: Request, db: Session = Depends(get_db), form_data: OAuth2PasswordRequestForm = Depends()):
    owner = crud.get_owner_by_email(db, email=form_data.username)
    if not owner or not security.verify_password(form_data.password, owner.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=request.state.gettext("Incorrect email or password"),
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": owner.email}, expires_delta=access_token_expires
    )
    # Redirect to dashboard after successful login
    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    response.set_cookie(key="access_token", value=access_token, httponly=True, max_age=access_token_expires.total_seconds())
    response.set_cookie(key="token_type", value="bearer", httponly=True, max_age=access_token_expires.total_seconds())
    return response

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request, db: Session = Depends(get_db)):
    _ = request.state.gettext
    return templates.TemplateResponse("index.html", {"request": request, "languages": LANGUAGES, "_": _})

@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    _ = request.state.gettext
    return templates.TemplateResponse("register.html", {"request": request, "languages": LANGUAGES, "_": _})

@app.post("/register", response_class=HTMLResponse)
async def register_owner(request: Request, db: Session = Depends(get_db),
                         name: str = Form(...), email: str = Form(...),
                         password: str = Form(...), phone: Optional[str] = Form(None)):
    _ = request.state.gettext
    db_owner = crud.get_owner_by_email(db, email=email)
    if db_owner:
        return templates.TemplateResponse("register.html", {"request": request, "error": _("Email already registered"), "languages": LANGUAGES, "_": _})

    hashed_password = security.get_password_hash(password)
    owner_create = schemas.OwnerCreate(name=name, email=email, password=password, phone=phone)
    owner = crud.create_owner(db=db, owner=owner_create, hashed_password=hashed_password)

    # Log in the owner immediately after registration
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": owner.email}, expires_delta=access_token_expires
    )
    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    response.set_cookie(key="access_token", value=access_token, httponly=True, max_age=access_token_expires.total_seconds())
    response.set_cookie(key="token_type", value="bearer", httponly=True, max_age=access_token_expires.total_seconds())
    return response

@app.get("/dashboard", response_class=HTMLResponse)
async def owner_dashboard(request: Request, db: Session = Depends(get_db), current_owner: models.Owner = Depends(security.get_current_owner)):
    _ = request.state.gettext
    services = crud.get_owner_services(db, owner_id=current_owner.id)
    bookings = crud.get_owner_upcoming_bookings(db, owner_id=current_owner.id)
    analytics_data = crud.get_owner_analytics(db, owner_id=current_owner.id)
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "owner": current_owner,
        "services": services,
        "bookings": bookings,
        "analytics": analytics_data,
        "languages": LANGUAGES,
        "_": _,
        "settings": settings,
        "stripe_public_key": settings.STRIPE_PUBLIC_KEY
    })

@app.post("/dashboard/profile", response_class=HTMLResponse)
async def update_owner_profile_endpoint(request: Request, db: Session = Depends(get_db),
                                        current_owner: models.Owner = Depends(security.get_current_owner),
                                        name: str = Form(...), phone: Optional[str] = Form(None)):
    _ = request.state.gettext
    try:
        owner_update = schemas.OwnerProfileUpdate(name=name, phone=phone)
        crud.update_owner_profile(db, current_owner, owner_update)
        return RedirectResponse(url="/dashboard?message=" + _("Profile updated successfully!"), status_code=status.HTTP_302_FOUND)
    except Exception as e:
        return RedirectResponse(url="/dashboard?error=" + _("Error updating profile: ") + str(e), status_code=status.HTTP_302_FOUND)

@app.get("/logout", response_class=HTMLResponse)
async def logout(response: Response):
    response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    response.delete_cookie(key="access_token")
    response.delete_cookie(key="token_type")
    return response

@app.get("/{owner_name}", response_class=HTMLResponse)
async def booking_page(request: Request, owner_name: str, db: Session = Depends(get_db)):
    _ = request.state.gettext
    owner = db.query(models.Owner).filter(models.Owner.name == owner_name).first()
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Owner not found"))

    services = crud.get_owner_services(db, owner_id=owner.id)
    if not services:
        return templates.TemplateResponse("booking_page.html", {
            "request": request,
            "owner": owner,
            "services": [],
            "error": _("No services available for this owner."),
            "languages": LANGUAGES,
            "_": _
        })

    # Group availability by service
    services_with_availability = []
    for service in services:
        availability_slots = []
        for avail in service.availability:
            availability_slots.append({
                "day_of_week": avail.day_of_week,
                "start_time": avail.start_time,
                "end_time": avail.end_time
            })
        services_with_availability.append({
            "id": service.id,
            "name": service.name,
            "description": service.description,
            "duration_minutes": service.duration_minutes,
            "price": service.price,
            "availability": availability_slots
        })

    return templates.TemplateResponse("booking_page.html", {
        "request": request,
        "owner": owner,
        "services": services_with_availability,
        "languages": LANGUAGES,
        "_": _
    })

@app.post("/{owner_name}/book", response_class=HTMLResponse)
async def submit_booking(request: Request, owner_name: str, db: Session = Depends(get_db),
                         service_id: int = Form(...),
                         customer_name: str = Form(...),
                         customer_email: EmailStr = Form(...),
                         customer_phone: Optional[str] = Form(None),
                         booking_date: str = Form(...),
                         booking_time_str: str = Form(...)):
    _ = request.state.gettext
    owner = db.query(models.Owner).filter(models.Owner.name == owner_name).first()
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Owner not found"))

    service = crud.get_service_by_id(db, service_id=service_id)
    if not service or service.owner_id != owner.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Service not found for this owner"))

    try:
        # Combine date and time string and parse with timezone awareness
        booking_datetime_str = f"{booking_date} {booking_time_str}"
        # Assume UTC for stored times, or a specific timezone for the owner
        # For simplicity, let's assume incoming booking_time_str is in owner's local time (if specified)
        # or just parse as naive and then localize (or assume UTC for now)
        # For now, let's treat booking_datetime_str as naive and convert to UTC for storage
        booking_datetime_naive = datetime.strptime(booking_datetime_str, "%Y-%m-%d %H:%M")
        booking_datetime_utc = pytz.utc.localize(booking_datetime_naive) # Assuming naive datetime is UTC for simplicity

        # Basic availability check (needs to be more robust for real-world)
        # This is a minimal check; actual implementation needs to consider service duration, existing bookings, etc.
        # For MVP, we assume the UI only presents available slots.
        # This part requires a more sophisticated calendar/scheduling library as per roadmap.

        booking_data = schemas.BookingCreate(
            service_id=service.id,
            customer_name=customer_name,
            customer_email=customer_email,
            customer_phone=customer_phone,
            booking_time=booking_datetime_utc
        )
        booking = crud.create_booking(db, booking_data, owner_id=owner.id)

        # Send notifications
        notifications.send_owner_notification(owner, service, booking)
        notifications.send_customer_confirmation(owner, service, booking)

        # Redirect to a confirmation page
        return RedirectResponse(url=f"/{owner_name}/booking-confirmation/{booking.id}", status_code=status.HTTP_302_FOUND)

    except ValueError:
        return templates.TemplateResponse("booking_page.html", {
            "request": request,
            "owner": owner,
            "services": crud.get_owner_services(db, owner.id),
            "error": _("Invalid date or time format."),
            "languages": LANGUAGES,
            "_": _
        })
    except Exception as e:
        # Log the error for debugging
        print(f"Booking error: {e}")
        return templates.TemplateResponse("booking_page.html", {
            "request": request,
            "owner": owner,
            "services": crud.get_owner_services(db, owner.id),
            "error": _("An error occurred during booking. Please try again."),
            "languages": LANGUAGES,
            "_": _
        })

@app.get("/{owner_name}/booking-confirmation/{booking_id}", response_class=HTMLResponse)
async def booking_confirmation_page(request: Request, owner_name: str, booking_id: int, db: Session = Depends(get_db)):
    _ = request.state.gettext
    owner = db.query(models.Owner).filter(models.Owner.name == owner_name).first()
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Owner not found"))

    booking = db.query(models.Booking).filter(models.Booking.id == booking_id, models.Booking.owner_id == owner.id).first()
    if not booking:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Booking not found"))

    service = crud.get_service_by_id(db, booking.service_id)
    if not service:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Service not found for this booking"))

    # Pass the locale-aware formatters to the template
    return templates.TemplateResponse("booking_confirmation.html", {
        "request": request,
        "owner": owner,
        "booking": booking,
        "service": service,
        "languages": LANGUAGES,
        "_": _
    })

# Stripe related endpoints
@app.post("/create-checkout-session")
async def create_checkout_session(request: Request, current_owner: models.Owner = Depends(security.get_current_owner), db: Session = Depends(get_db)):
    _ = request.state.gettext
    try:
        if not settings.STRIPE_PRICE_ID:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=_("Stripe Price ID is not configured."))

        checkout_session = stripe.checkout.Session.create(
            line_items=[
                {
                    'price': settings.STRIPE_PRICE_ID,
                    'quantity': 1,
                },
            ],
            mode='subscription',
            success_url=f"{settings.SERVER_NAME}/dashboard?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{settings.SERVER_NAME}/dashboard?canceled=true",
            customer_email=current_owner.email,
            client_reference_id=str(current_owner.id),
            metadata={
                "owner_id": current_owner.id,
                "owner_email": current_owner.email,
            }
        )
        return RedirectResponse(checkout_session.url, status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=_("Error creating checkout session: ") + str(e))

@app.post("/stripe-webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    _ = request.state.gettext
    payload = await request.body()
    sig_header = request.headers.get('stripe-signature')

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError as e:
        # Invalid payload
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_("Invalid payload"))
    except stripe.error.SignatureVerificationError as e:
        # Invalid signature
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_("Invalid signature"))

    # Handle the event
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        owner_id = session.get('metadata', {}).get('owner_id')
        customer_id = session.get('customer')
        subscription_id = session.get('subscription')

        if owner_id and customer_id and subscription_id:
            owner = crud.get_owner(db, int(owner_id))
            if owner:
                crud.update_owner_subscription_status(db, owner, "premium", stripe_customer_id=customer_id, stripe_subscription_id=subscription_id)
                print(f"Owner {owner.id} upgraded to premium. Customer ID: {customer_id}, Subscription ID: {subscription_id}")
            else:
                print(f"Owner with ID {owner_id} not found for subscription update.")
        else:
            print("Missing owner_id, customer_id, or subscription_id in checkout.session.completed event.")

    elif event['type'] == 'customer.subscription.deleted':
        subscription = event['data']['object']
        customer_id = subscription.get('customer')
        
        owner = db.query(models.Owner).filter(models.Owner.stripe_customer_id == customer_id).first()
        if owner:
            crud.update_owner_subscription_status(db, owner, "free", stripe_subscription_id=None)
            print(f"Owner {owner.id} subscription deleted. Reverted to free.")
        else:
            print(f"Owner with Stripe Customer ID {customer_id} not found for subscription deletion.")

    elif event['type'] == 'invoice.payment_failed':
        invoice = event['data']['object']
        customer_id = invoice.get('customer')
        # Optionally handle payment failures, e.g., notify owner
        print(f"Payment failed for customer {customer_id}.")

    return Response(status_code=status.HTTP_200_OK)

# Admin Endpoints
@app.post("/admin/token", response_model=schemas.Token)
async def admin_login_for_access_token(request: Request, db: Session = Depends(get_db), form_data: OAuth2PasswordRequestForm = Depends()):
    _ = request.state.gettext
    admin = crud.get_admin_by_email(db, email=form_data.username)
    if not admin or not security.verify_password(form_data.password, admin.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_("Incorrect admin email or password"),
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_admin_access_token(
        data={"sub": admin.email}, expires_delta=access_token_expires
    )
    # This token is for API access. For UI, we'll redirect and set cookie.
    response = RedirectResponse(url="/admin", status_code=status.HTTP_302_FOUND)
    response.set_cookie(key="admin_access_token", value=access_token, httponly=True, max_age=access_token_expires.total_seconds())
    response.set_cookie(key="admin_token_type", value="bearer", httponly=True, max_age=access_token_expires.total_seconds())
    return response

@app.get("/admin/login", response_class=HTMLResponse)
async def admin_login_page(request: Request):
    _ = request.state.gettext
    return templates.TemplateResponse("admin_login.html", {"request": request, "languages": LANGUAGES, "_": _})

@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard_page(request: Request, db: Session = Depends(get_db), current_admin: models.Admin = Depends(security.get_current_active_admin)):
    _ = request.state.gettext
    owners = crud.get_owners(db) # Fetch all owners for display
    return templates.TemplateResponse("admin_dashboard.html", {
        "request": request,
        "admin": current_admin,
        "owners": owners,
        "languages": LANGUAGES,
        "_": _
    })

@app.get("/admin/logout", response_class=HTMLResponse)
async def admin_logout(response: Response):
    response = RedirectResponse(url="/admin/login", status_code=status.HTTP_302_FOUND)
    response.delete_cookie(key="admin_access_token")
    response.delete_cookie(key="admin_token_type")
    return response

# API endpoints for admin to manage owners
@app.get("/admin/api/owners", response_model=List[schemas.Owner])
async def get_all_owners(db: Session = Depends(get_db), current_admin: models.Admin = Depends(security.get_current_active_admin), skip: int = 0, limit: int = 100):
    owners = crud.get_owners(db, skip=skip, limit=limit)
    return owners

@app.get("/admin/api/owners/{owner_id}", response_model=schemas.Owner)
async def get_owner_details(owner_id: int, db: Session = Depends(get_db), current_admin: models.Admin = Depends(security.get_current_active_admin)):
    owner = crud.get_owner(db, owner_id)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Owner not found")
    return owner

@app.put("/admin/api/owners/{owner_id}", response_model=schemas.Owner)
async def update_owner_details_by_admin(owner_id: int, owner_update: schemas.OwnerAdminUpdate, db: Session = Depends(get_db), current_admin: models.Admin = Depends(security.get_current_active_admin)):
    owner = crud.get_owner(db, owner_id)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Owner not found")
    updated_owner = crud.update_owner_by_admin(db, owner, owner_update)
    return updated_owner

@app.delete("/admin/api/owners/{owner_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_owner_by_admin(owner_id: int, db: Session = Depends(get_db), current_admin: models.Admin = Depends(security.get_current_active_admin)):
    success = crud.delete_owner(db, owner_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Owner not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
