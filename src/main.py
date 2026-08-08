from fastapi import FastAPI, Depends, HTTPException, status, Request, Form, Response, APIRouter
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from datetime import timedelta, datetime
import os
import stripe
from babel.dates import format_date, format_time, format_datetime
from babel.numbers import format_currency
from gettext import translation, bindtextdomain, textdomain
import locale as sys_locale # Not directly used for i18n, but for potential system locale queries if needed

# Import custom modules
from . import crud, models, schemas, security
from .database import SessionLocal, engine, get_db
from .config import settings
from .notifications import send_booking_confirmation_email, send_owner_notification_email, send_whatsapp_message

# Ensure tables are created
models.Base.metadata.create_all(bind=engine)

app = FastAPI()

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Templates setup
templates = Jinja2Templates(directory="templates")

# Stripe setup
stripe.api_key = settings.STRIPE_SECRET_KEY

# i18n setup
def get_locale(request: Request) -> str:
    lang_cookie = request.cookies.get("lang")
    if lang_cookie and lang_cookie in ["en", "ar", "fr"]:
        return lang_cookie
    return settings.DEFAULT_LOCALE

def get_translations(locale: str):
    try:
        # Ensure the domain is bound to the correct directory
        bindtextdomain('messages', settings.LOCALES_DIR)
        # Set the textdomain for the current process
        textdomain('messages')
        # Get the translation object for the specified locale
        _t = translation('messages', settings.LOCALES_DIR, languages=[locale]).gettext
    except Exception as e:
        print(f"Error loading translation for locale {locale}: {e}")
        _t = lambda x: x # Fallback to original string if translation fails
    return _t

@app.middleware("http")
async def add_i18n_context(request: Request, call_next):
    # Handle language setting from query param and update cookie
    lang_param = request.query_params.get("lang")
    if lang_param and lang_param in ["en", "ar", "fr"]:
        response = RedirectResponse(url=request.url.remove_query_params(keys=["lang"]), status_code=status.HTTP_302_FOUND)
        response.set_cookie(key="lang", value=lang_param, httponly=True, max_age=30*24*60*60) # 30 days
        return response

    locale = get_locale(request)
    _ = get_translations(locale)
    request.state.locale = locale
    request.state._ = _

    # Add Jinja2 globals for i18n
    templates.env.globals['gettext'] = _
    templates.env.globals['locale'] = locale
    templates.env.globals['format_datetime'] = lambda dt, format='medium': format_datetime(dt, format=format, locale=locale)
    templates.env.globals['format_date'] = lambda d, format='medium': format_date(d, format=format, locale=locale)
    templates.env.globals['format_time'] = lambda t, format='medium': format_time(t, format=format, locale=locale)
    
    # Currency formatting, assuming price is in cents and currency is 'USD' for simplicity in MVP
    # In a real app, currency should be configurable per owner/service
    templates.env.globals['format_currency'] = lambda amount, currency: format_currency(amount / 100, currency, locale=locale) # Assuming price is in cents

    response = await call_next(request)
    return response

# Root route
@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    _ = request.state._
    return templates.TemplateResponse("index.html", {"request": request, "title": _("Welcome to BookSlot")})

# Owner authentication routes
@app.post("/token", response_model=schemas.Token)
async def login_for_access_token(request: Request, db: Session = Depends(get_db), form_data: OAuth2PasswordRequestForm = Depends()):
    _ = request.state._
    owner = security.authenticate_owner(db, form_data.username, form_data.password)
    if not owner:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_("Incorrect username or password"),
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": owner.email}, expires_delta=access_token_expires
    )
    # Redirect to dashboard on successful login
    response = RedirectResponse(url=app.url_path_for("owner_dashboard"), status_code=status.HTTP_302_FOUND)
    response.set_cookie(key="access_token", value=f"Bearer {access_token}", httponly=True, max_age=access_token_expires.total_seconds())
    return response

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    _ = request.state._
    return templates.TemplateResponse("login.html", {"request": request, "title": _("Login")})

@app.get("/logout", response_class=RedirectResponse)
async def logout(request: Request):
    response = RedirectResponse(url=app.url_path_for("login_page"), status_code=status.HTTP_302_FOUND)
    response.delete_cookie(key="access_token")
    return response

@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    _ = request.state._
    return templates.TemplateResponse("register.html", {"request": request, "title": _("Register")})

@app.post("/register", response_class=RedirectResponse)
async def register_owner(request: Request, db: Session = Depends(get_db), name: str = Form(...), email: EmailStr = Form(...), phone: Optional[str] = Form(None), password: str = Form(...)):
    _ = request.state._
    db_owner = crud.get_owner_by_email(db, email=email)
    if db_owner:
        raise HTTPException(status_code=400, detail=_("Email already registered"))

    hashed_password = security.get_password_hash(password)
    owner_create = schemas.OwnerCreate(name=name, email=email, phone=phone, password=password) # password is not hashed yet in schema
    owner = crud.create_owner(db=db, owner=owner_create, hashed_password=hashed_password)
    
    # Auto-login after registration
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": owner.email}, expires_delta=access_token_expires
    )
    response = RedirectResponse(url=app.url_path_for("owner_dashboard"), status_code=status.HTTP_302_FOUND)
    response.set_cookie(key="access_token", value=f"Bearer {access_token}", httponly=True, max_age=access_token_expires.total_seconds())
    return response

# Owner dashboard and profile management
@app.get("/dashboard", response_class=HTMLResponse)
async def owner_dashboard(request: Request, current_user: models.Owner = Depends(security.get_current_active_owner), db: Session = Depends(get_db)):
    _ = request.state._
    bookings = crud.get_owner_upcoming_bookings(db, owner_id=current_user.id)
    services = crud.get_owner_services(db, owner_id=current_user.id)
    return templates.TemplateResponse("dashboard.html", {"request": request, "owner": current_user, "bookings": bookings, "services": services, "title": _("Dashboard")})

@app.get("/profile", response_class=HTMLResponse)
async def owner_profile_page(request: Request, current_user: models.Owner = Depends(security.get_current_active_owner)):
    _ = request.state._
    return templates.TemplateResponse("profile.html", {"request": request, "owner": current_user, "title": _("Profile")})

@app.post("/profile", response_class=RedirectResponse)
async def update_owner_profile(
    request: Request,
    current_user: models.Owner = Depends(security.get_current_active_owner),
    db: Session = Depends(get_db),
    name: str = Form(...),
    phone: Optional[str] = Form(None)
):
    _ = request.state._
    owner_update = schemas.OwnerProfileUpdate(name=name, phone=phone if phone else None)
    try:
        crud.update_owner_profile(db, current_user, owner_update)
        return RedirectResponse(url=app.url_path_for("owner_profile_page"), status_code=status.HTTP_302_FOUND)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

# Public booking page
@app.get("/book/{owner_name}", response_class=HTMLResponse)
async def booking_page(request: Request, owner_name: str, db: Session = Depends(get_db)):
    _ = request.state._
    owner = db.query(models.Owner).filter(models.Owner.name == owner_name).first()
    if not owner:
        raise HTTPException(status_code=404, detail=_("Owner not found"))
    services = crud.get_owner_services(db, owner.id)
    return templates.TemplateResponse("booking_page.html", {"request": request, "owner": owner, "services": services, "title": _("Book an Appointment")})

@app.post("/book/{owner_name}/submit", response_class=RedirectResponse)
async def submit_booking(
    request: Request,
    owner_name: str,
    db: Session = Depends(get_db),
    customer_name: str = Form(...),
    customer_email: EmailStr = Form(...),
    customer_phone: Optional[str] = Form(None),
    booking_date: str = Form(...), # YYYY-MM-DD
    booking_time: str = Form(...), # HH:MM
    service_id: int = Form(...)
):
    _ = request.state._
    owner = db.query(models.Owner).filter(models.Owner.name == owner_name).first()
    if not owner:
        raise HTTPException(status_code=404, detail=_("Owner not found"))

    service = crud.get_service_by_id(db, service_id)
    if not service or service.owner_id != owner.id:
        raise HTTPException(status_code=400, detail=_("Invalid service selected"))

    try:
        booking_datetime_str = f"{booking_date} {booking_time}"
        booking_dt = datetime.strptime(booking_datetime_str, "%Y-%m-%d %H:%M")
    except ValueError:
        raise HTTPException(status_code=400, detail=_("Invalid date or time format"))

    if booking_dt < datetime.now():
        raise HTTPException(status_code=400, detail=_("Booking time cannot be in the past"))

    booking_data = schemas.BookingCreate(
        customer_name=customer_name,
        customer_email=customer_email,
        customer_phone=customer_phone if customer_phone else None,
        booking_time=booking_dt,
        service_id=service_id
    )
    
    try:
        db_booking = crud.create_booking(db, booking_data, owner.id)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # Send notifications
    try:
        await send_booking_confirmation_email(owner, db_booking, service)
        await send_owner_notification_email(owner, db_booking, service)
        if owner.phone and settings.TWILIO_WHATSAPP_NUMBER: # Only send WhatsApp if owner has phone and Twilio is configured
            await send_whatsapp_message(owner, db_booking, service)
    except Exception as e:
        # Log the error but don't prevent booking completion
        print(f"Notification sending failed: {e}")

    return RedirectResponse(url=app.url_path_for("booking_confirmation_page"), status_code=status.HTTP_302_FOUND)

@app.get("/booking-confirmation", response_class=HTMLResponse)
async def booking_confirmation_page(request: Request):
    _ = request.state._
    return templates.TemplateResponse("booking_confirmation.html", {"request": request, "title": _("Booking Confirmed")})

# Stripe payment and subscription management
@app.post("/create-checkout-session")
async def create_checkout_session(
    request: Request,
    current_user: models.Owner = Depends(security.get_current_active_owner),
    db: Session = Depends(get_db)
):
    _ = request.state._
    try:
        checkout_session = stripe.checkout.Session.create(
            line_items=[
                {
                    'price': settings.STRIPE_PRICE_ID,
                    'quantity': 1,
                },
            ],
            mode='subscription',
            success_url=f"{settings.SERVER_NAME}/dashboard?success=true",
            cancel_url=f"{settings.SERVER_NAME}/subscription-management?cancelled=true",
            customer_email=current_user.email,
            client_reference_id=str(current_user.id) # Link to owner in Stripe
        )
        return RedirectResponse(checkout_session.url, status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@app.post("/stripe-webhook")
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
        customer_id = session.get('customer')
        subscription_id = session.get('subscription')

        if owner_id and customer_id and subscription_id:
            owner = crud.get_owner(db, int(owner_id))
            if owner:
                crud.update_owner_subscription_status(db, owner, "premium", customer_id, subscription_id)
                print(f"Owner {owner.id} upgraded to premium. Stripe Customer ID: {customer_id}, Subscription ID: {subscription_id}")
            else:
                print(f"Owner with ID {owner_id} not found for subscription update.")

    elif event['type'] == 'customer.subscription.deleted':
        subscription = event['data']['object']
        customer_id = subscription.get('customer')

        owner = db.query(models.Owner).filter(models.Owner.stripe_customer_id == customer_id).first()
        if owner:
            crud.update_owner_subscription_status(db, owner, "cancelled")
            print(f"Owner {owner.id} subscription cancelled.")
        else:
            print(f"Owner with Stripe Customer ID {customer_id} not found for subscription cancellation.")

    return Response(status_code=200)

@app.get("/analytics", response_model=schemas.OwnerAnalytics)
async def get_owner_analytics_data(current_user: models.Owner = Depends(security.get_current_active_owner), db: Session = Depends(get_db)):
    _ = request.state._
    analytics_data = crud.get_owner_analytics(db, current_user.id)
    return schemas.OwnerAnalytics(**analytics_data)

@app.get("/subscription-management", response_class=HTMLResponse)
async def subscription_management_page(request: Request, current_user: models.Owner = Depends(security.get_current_active_owner)):
    _ = request.state._
    stripe_public_key = settings.STRIPE_PUBLIC_KEY
    return templates.TemplateResponse("subscription_management.html", {
        "request": request,
        "owner": current_user,
        "stripe_public_key": stripe_public_key,
        "title": _("Subscription Management")
    })

# Admin specific routes
admin_router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(security.get_current_admin_user)], # All admin routes require admin privileges
    responses={403: {"description": "Not authenticated as admin"}},
)

@admin_router.get("/dashboard", response_class=HTMLResponse)
async def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    _ = request.state._
    owners = crud.get_owners(db)
    return templates.TemplateResponse("admin_dashboard.html", {"request": request, "owners": owners, "title": _("Admin Dashboard")})

@admin_router.get("/owners/{owner_id}", response_class=HTMLResponse)
async def admin_owner_detail(request: Request, owner_id: int, db: Session = Depends(get_db)):
    _ = request.state._
    owner = crud.get_owner(db, owner_id=owner_id)
    if not owner:
        raise HTTPException(status_code=404, detail=_("Owner not found"))
    return templates.TemplateResponse("admin_owner_detail.html", {"request": request, "owner": owner, "title": _("Manage Owner")})

@admin_router.post("/owners/{owner_id}/update", response_class=RedirectResponse)
async def admin_update_owner(
    request: Request,
    owner_id: int,
    name: str = Form(...),
    email: EmailStr = Form(...),
    phone: Optional[str] = Form(None),
    subscription_status: str = Form(...),
    is_admin: bool = Form(False),
    db: Session = Depends(get_db)
):
    _ = request.state._
    owner = crud.get_owner(db, owner_id=owner_id)
    if not owner:
        raise HTTPException(status_code=404, detail=_("Owner not found"))

    owner_update = schemas.OwnerAdminUpdate(
        name=name,
        email=email,
        phone=phone if phone else None,
        subscription_status=subscription_status,
        is_admin=is_admin
    )
    crud.update_owner_by_admin(db, owner, owner_update)
    return RedirectResponse(url=app.url_path_for("admin_owner_detail", owner_id=owner_id), status_code=status.HTTP_302_FOUND)

@admin_router.post("/owners/{owner_id}/delete", response_class=RedirectResponse)
async def admin_delete_owner(request: Request, owner_id: int, db: Session = Depends(get_db)):
    _ = request.state._
    success = crud.delete_owner(db, owner_id=owner_id)
    if not success:
        raise HTTPException(status_code=404, detail=_("Owner not found"))
    return RedirectResponse(url=app.url_path_for("admin_dashboard"), status_code=status.HTTP_302_FOUND)

app.include_router(admin_router)
