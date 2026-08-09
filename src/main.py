from fastapi import FastAPI, Depends, HTTPException, status, Request, Form, Response
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, date, time
from typing import List, Annotated, Optional
import gettext
import os
import secrets
import json
import stripe
import uuid # Import uuid for recurrence_id generation

from . import models, schemas, security, analytics, availability_utils, notifications
from .config import settings
from .database import engine, SessionLocal

# Create database tables
models.Base.metadata.create_all(bind=engine)

app = FastAPI()

# Jinja2 Templates setup
templates_dir = os.path.join(os.path.dirname(__file__), "../templates")
templates = Jinja2Templates(directory=templates_dir)

# Internationalization setup
locales_dir = os.path.join(os.path.dirname(__file__), "../locales")
_ = gettext.gettext # Default to no translation

@app.middleware("http")
async def add_i18n_middleware(request: Request, call_next):
    lang = request.cookies.get("lang", "en")
    
    # Gettext setup
    try:
        current_locale = gettext.translation("messages", locales_dir, languages=[lang])
        request.state.gettext = current_locale.gettext
    except FileNotFoundError:
        # Fallback to English if locale file not found
        request.state.gettext = gettext.gettext

    request.state.lang = lang
    response = await call_next(request)
    return response

@app.context_processor
def inject_gettext_and_lang(request: Request):
    return {"_": request.state.gettext, "lang": request.state.lang}

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# OAuth2PasswordBearer for token authentication
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

async def get_current_owner(token: Annotated[str, Depends(oauth2_scheme)], db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    owner = security.get_current_owner(db, token)
    if owner is None:
        raise credentials_exception
    return owner

async def get_current_active_owner(current_owner: Annotated[models.Owner, Depends(get_current_owner)]):
    if not current_owner.is_active:
        raise HTTPException(status_code=400, detail="Inactive owner")
    return current_owner

# Root redirect to login/register
@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# Authentication endpoints
@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@app.post("/register", response_class=HTMLResponse)
async def register_owner(request: Request, db: Session = Depends(get_db),
                         username: str = Form(...), email: str = Form(...), password: str = Form(...),
                         phone_number: Optional[str] = Form(None)):
    _ = request.state.gettext
    owner = db.query(models.Owner).filter(models.Owner.username == username).first()
    if owner:
        return templates.TemplateResponse("register.html", {"request": request, "error": _("Username already registered")})
    owner = db.query(models.Owner).filter(models.Owner.email == email).first()
    if owner:
        return templates.TemplateResponse("register.html", {"request": request, "error": _("Email already registered")})

    hashed_password = security.get_password_hash(password)
    new_owner = models.Owner(username=username, email=email, hashed_password=hashed_password, phone_number=phone_number)
    db.add(new_owner)
    db.commit()
    db.refresh(new_owner)
    return templates.TemplateResponse("register.html", {"request": request, "message": _("Registration successful! Please log in.")})

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, message: Optional[str] = None):
    return templates.TemplateResponse("login.html", {"request": request, "message": message})

@app.post("/login")
async def login_for_access_token(request: Request, db: Session = Depends(get_db), form_data: OAuth2PasswordRequestForm = Depends()):
    _ = request.state.gettext
    owner = security.authenticate_owner(db, form_data.username, form_data.password)
    if not owner:
        return templates.TemplateResponse("login.html", {"request": request, "error": _("Incorrect username or password")})
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": owner.username}, expires_delta=access_token_expires
    )
    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    response.set_cookie(key="access_token", value=access_token, httponly=True, max_age=access_token_expires.total_seconds())
    response.set_cookie(key="lang", value=owner.language, max_age=365 * 24 * 60 * 60) # Set language cookie
    return response

@app.get("/logout")
async def logout(response: Response):
    response = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    response.delete_cookie(key="access_token")
    return response

@app.post("/token", response_model=schemas.Token)
async def login_access_token(db: Session = Depends(get_db), form_data: OAuth2PasswordRequestForm = Depends()):
    owner = security.authenticate_owner(db, form_data.username, form_data.password)
    if not owner:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": owner.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

# Owner profile update
@app.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request, current_owner: Annotated[models.Owner, Depends(get_current_active_owner)]):
    return templates.TemplateResponse("profile.html", {"request": request, "owner": current_owner})

@app.post("/profile", response_class=HTMLResponse)
async def update_owner_profile(request: Request, db: Session = Depends(get_db),
                               current_owner: Annotated[models.Owner, Depends(get_current_active_owner)],
                               username: Optional[str] = Form(None),
                               email: Optional[EmailStr] = Form(None),
                               phone_number: Optional[str] = Form(None),
                               language: Optional[str] = Form(None)):
    _ = request.state.gettext
    if username and username != current_owner.username:
        if db.query(models.Owner).filter(models.Owner.username == username).first():
            return templates.TemplateResponse("profile.html", {"request": request, "owner": current_owner, "error": _("Username already taken.")})
        current_owner.username = username
    if email and email != current_owner.email:
        if db.query(models.Owner).filter(models.Owner.email == email).first():
            return templates.TemplateResponse("profile.html", {"request": request, "owner": current_owner, "error": _("Email already taken.")})
        current_owner.email = email
    if phone_number is not None:
        current_owner.phone_number = phone_number
    if language and language != current_owner.language:
        current_owner.language = language
        response = templates.TemplateResponse("profile.html", {"request": request, "owner": current_owner, "message": _("Profile updated successfully!")})
        response.set_cookie(key="lang", value=language, max_age=365 * 24 * 60 * 60)
        return response

    db.commit()
    db.refresh(current_owner)
    return templates.TemplateResponse("profile.html", {"request": request, "owner": current_owner, "message": _("Profile updated successfully!")})

# Service management
@app.get("/services", response_class=HTMLResponse)
async def services_page(request: Request, db: Session = Depends(get_db), current_owner: Annotated[models.Owner, Depends(get_current_active_owner)]):
    services = db.query(models.Service).filter(models.Service.owner_id == current_owner.id).all()
    return templates.TemplateResponse("services.html", {"request": request, "owner": current_owner, "services": services})

@app.post("/services", response_class=HTMLResponse)
async def create_service(request: Request, db: Session = Depends(get_db), current_owner: Annotated[models.Owner, Depends(get_current_active_owner)],
                         name: str = Form(...), description: Optional[str] = Form(None), duration_minutes: int = Form(...), price: int = Form(...)):
    _ = request.state.gettext
    new_service = models.Service(owner_id=current_owner.id, name=name, description=description, duration_minutes=duration_minutes, price=price)
    db.add(new_service)
    db.commit()
    db.refresh(new_service)
    return RedirectResponse(url="/services", status_code=status.HTTP_302_FOUND)

# Availability management
@app.get("/availability", response_class=HTMLResponse)
async def availability_page(request: Request, db: Session = Depends(get_db), current_owner: Annotated[models.Owner, Depends(get_current_active_owner)]):
    services = db.query(models.Service).filter(models.Service.owner_id == current_owner.id).all()
    availabilities = db.query(models.Availability).filter(models.Availability.owner_id == current_owner.id).all()
    return templates.TemplateResponse("availability.html", {"request": request, "owner": current_owner, "services": services, "availabilities": availabilities, "recurrence_types": models.RecurrenceType})

@app.post("/availability", response_class=HTMLResponse)
async def create_availability(request: Request, db: Session = Depends(get_db), current_owner: Annotated[models.Owner, Depends(get_current_active_owner)],
                              service_id: Optional[int] = Form(None),
                              date: Optional[date] = Form(None),
                              start_time: time = Form(...),
                              end_time: time = Form(...),
                              recurrence_type: models.RecurrenceType = Form(models.RecurrenceType.NONE),
                              recurrence_value: Optional[str] = Form(None),
                              recurrence_start_date: Optional[date] = Form(None),
                              recurrence_end_date: Optional[date] = Form(None)):
    _ = request.state.gettext
    
    if recurrence_type == models.RecurrenceType.NONE:
        if not date:
            return templates.TemplateResponse("availability.html", {"request": request, "owner": current_owner, "error": _("Date is required for one-off availability.")})
        if recurrence_start_date or recurrence_end_date or recurrence_value:
            return templates.TemplateResponse("availability.html", {"request": request, "owner": current_owner, "error": _("Recurrence fields should be empty for one-off availability.")})
    else: # Recurring availability
        if date:
            return templates.TemplateResponse("availability.html", {"request": request, "owner": current_owner, "error": _("Date should be empty for recurring availability.")})
        if not recurrence_start_date:
            return templates.TemplateResponse("availability.html", {"request": request, "owner": current_owner, "error": _("Recurrence start date is required for recurring availability.")})
        if recurrence_type != models.RecurrenceType.DAILY and not recurrence_value:
             return templates.TemplateResponse("availability.html", {"request": request, "owner": current_owner, "error": _("Recurrence value is required for weekly/monthly recurrence.")})

    new_availability = models.Availability(
        owner_id=current_owner.id,
        service_id=service_id if service_id != 0 else None,
        date=date,
        start_time=start_time,
        end_time=end_time,
        recurrence_type=recurrence_type,
        recurrence_value=recurrence_value,
        recurrence_start_date=recurrence_start_date,
        recurrence_end_date=recurrence_end_date,
    )
    db.add(new_availability)
    db.commit()
    db.refresh(new_availability)
    return RedirectResponse(url="/availability", status_code=status.HTTP_302_FOUND)


# Public booking page
@app.get("/book/{owner_username}", response_class=HTMLResponse)
async def booking_page(request: Request, owner_username: str, db: Session = Depends(get_db), service_id: Optional[int] = None, selected_date: Optional[date] = None):
    _ = request.state.gettext
    owner = db.query(models.Owner).filter(models.Owner.username == owner_username).first()
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Owner not found"))

    services = db.query(models.Service).filter(models.Service.owner_id == owner.id).all()
    selected_service = None
    if service_id:
        selected_service = db.query(models.Service).filter(models.Service.id == service_id, models.Service.owner_id == owner.id).first()
    if not selected_service and services:
        selected_service = services[0] # Default to the first service

    available_slots = []
    if selected_service and selected_date:
        available_slots = availability_utils.get_available_slots_for_day(db, owner.id, selected_service.id, selected_date, selected_service.duration_minutes)

    return templates.TemplateResponse(
        "booking_page.html",
        {
            "request": request,
            "owner": owner,
            "services": services,
            "selected_service": selected_service,
            "selected_date": selected_date,
            "available_slots": available_slots,
            "today": date.today(),
            "error": None
        },
    )

@app.post("/book/{owner_username}/submit", response_class=HTMLResponse)
async def submit_booking(request: Request, owner_username: str, db: Session = Depends(get_db),
                         service_id: int = Form(...),
                         booking_date: date = Form(...),
                         booking_time: time = Form(...),
                         customer_name: str = Form(...),
                         customer_email: EmailStr = Form(...),
                         customer_phone_number: Optional[str] = Form(None),
                         recurrence_type: models.RecurrenceType = Form(models.RecurrenceType.NONE),
                         recurrence_value: Optional[str] = Form(None),
                         recurrence_end_date: Optional[date] = Form(None)):
    _ = request.state.gettext
    owner = db.query(models.Owner).filter(models.Owner.username == owner_username).first()
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Owner not found"))

    service = db.query(models.Service).filter(models.Service.id == service_id, models.Service.owner_id == owner.id).first()
    if not service:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Service not found"))

    customer = db.query(models.Customer).filter(models.Customer.email == customer_email).first()
    if not customer:
        customer = models.Customer(name=customer_name, email=customer_email, phone_number=customer_phone_number)
        db.add(customer)
        db.commit()
        db.refresh(customer)
    else:
        customer.name = customer_name
        customer.phone_number = customer_phone_number
        db.commit()
        db.refresh(customer)

    if recurrence_type != models.RecurrenceType.NONE and recurrence_end_date and recurrence_end_date >= booking_date:
        recurrence_id = uuid.uuid4()
        current_date = booking_date
        while current_date <= recurrence_end_date:
            is_available_on_this_date = False
            if recurrence_type == models.RecurrenceType.DAILY:
                is_available_on_this_date = True
            elif recurrence_type == models.RecurrenceType.WEEKLY and recurrence_value:
                target_weekday_name = current_date.strftime('%a').upper()
                if target_weekday_name in [d.strip().upper() for d in recurrence_value.split(',')]:
                    is_available_on_this_date = True
            elif recurrence_type == models.RecurrenceType.MONTHLY and recurrence_value:
                try:
                    day_of_month = int(recurrence_value)
                    if current_date.day == day_of_month:
                        is_available_on_this_date = True
                except ValueError:
                    pass

            if is_available_on_this_date:
                available_slots_for_day = availability_utils.get_available_slots_for_day(db, owner.id, service.id, current_date, service.duration_minutes)
                if booking_time in available_slots_for_day:
                    booking = models.Booking(
                        owner_id=owner.id,
                        service_id=service.id,
                        customer_id=customer.id,
                        date=current_date,
                        time=booking_time,
                        recurrence_id=recurrence_id
                    )
                    db.add(booking)
                    db.commit()
                    db.refresh(booking)
                    notifications.send_booking_confirmation(owner, customer, service, booking, _=_)

            current_date += timedelta(days=1)
    else:
        available_slots_for_day = availability_utils.get_available_slots_for_day(db, owner.id, service.id, booking_date, service.duration_minutes)
        if booking_time not in available_slots_for_day:
            return templates.TemplateResponse(
                "booking_page.html",
                {
                    "request": request,
                    "owner": owner,
                    "services": db.query(models.Service).filter(models.Service.owner_id == owner.id).all(),
                    "selected_service": service,
                    "selected_date": booking_date,
                    "available_slots": available_slots_for_day,
                    "today": date.today(),
                    "error": _("Selected time slot is no longer available.")
                },
                status_code=status.HTTP_400_BAD_REQUEST
            )

        booking = models.Booking(
            owner_id=owner.id,
            service_id=service.id,
            customer_id=customer.id,
            date=booking_date,
            time=booking_time
        )
        db.add(booking)
        db.commit()
        db.refresh(booking)
        notifications.send_booking_confirmation(owner, customer, service, booking, _=_)

    return templates.TemplateResponse("booking_confirmation.html", {"request": request, "owner": owner, "service": service, "customer": customer, "booking_date": booking_date, "booking_time": booking_time, "_": _})


# Owner Dashboard
@app.get("/dashboard", response_class=HTMLResponse)
async def owner_dashboard(request: Request, db: Session = Depends(get_db), current_owner: Annotated[models.Owner, Depends(get_current_active_owner)]):
    _ = request.state.gettext

    bookings_with_details = db.query(models.Booking, models.Service, models.Customer).
        join(models.Service, models.Booking.service_id == models.Service.id).
        join(models.Customer, models.Booking.customer_id == models.Customer.id).
        filter(models.Booking.owner_id == current_owner.id).
        order_by(models.Booking.date, models.Booking.time).
        all()

    display_bookings = []
    for booking, service, customer in bookings_with_details:
        display_bookings.append({
            "id": booking.id,
            "date": booking.date,
            "time": booking.time,
            "service_name": service.name,
            "customer_name": customer.name,
            "customer_phone": customer.phone_number,
            "customer_email": customer.email,
            "is_recurring_instance": booking.recurrence_id is not None,
            "recurrence_id": booking.recurrence_id
        })

    monthly_bookings_data = analytics.get_monthly_bookings_data(db, current_owner.id)
    popular_services_data = analytics.get_popular_services_data(db, current_owner.id)

    subscription = db.query(models.Subscription).filter(models.Subscription.owner_id == current_owner.id, models.Subscription.status == "active").first()
    subscription_status = schemas.SubscriptionStatus(
        status=current_owner.subscription_status,
        current_period_end=subscription.current_period_end if subscription else None,
        plan_id=subscription.plan_id if subscription else "free",
        is_premium=current_owner.subscription_status == "premium"
    )

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "owner": current_owner,
            "bookings": display_bookings,
            "monthly_bookings_data": json.dumps(monthly_bookings_data),
            "popular_services_data": json.dumps(popular_services_data),
            "subscription_status": subscription_status,
            "_": _
        },
    )

# Analytics API endpoints
@app.get("/api/analytics/monthly-bookings", response_model=List[dict])
async def get_monthly_bookings(db: Session = Depends(get_db), current_owner: Annotated[models.Owner, Depends(get_current_active_owner)]):
    return analytics.get_monthly_bookings_data(db, current_owner.id)

@app.get("/api/analytics/popular-services", response_model=List[dict])
async def get_popular_services(db: Session = Depends(get_db), current_owner: Annotated[models.Owner, Depends(get_current_active_owner)]):
    return analytics.get_popular_services_data(db, current_owner.id)

# Stripe Payment Gateway and Subscription Management
stripe.api_key = settings.STRIPE_API_KEY

@app.post("/create-checkout-session")
async def create_checkout_session(request: Request, current_owner: Annotated[models.Owner, Depends(get_current_active_owner)]):
    _ = request.state.gettext
    if current_owner.subscription_status == "premium":
        raise HTTPException(status_code=400, detail=_("Owner already has a premium subscription."))

    try:
        checkout_session = stripe.checkout.Session.create(
            customer=current_owner.stripe_customer_id,
            line_items=[
                {
                    "price": settings.STRIPE_PREMIUM_PRICE_ID,
                    "quantity": 1,
                },
            ],
            mode="subscription",
            success_url=request.url_for("subscription_success").__str__() + "?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=request.url_for("subscription_cancel").__str__(),
            metadata={"owner_id": current_owner.id},
        )
        return RedirectResponse(url=checkout_session.url, status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/subscription/success", response_class=HTMLResponse)
async def subscription_success(request: Request, db: Session = Depends(get_db), session_id: str = None):
    _ = request.state.gettext
    if session_id:
        try:
            session = stripe.checkout.Session.retrieve(session_id)
            return templates.TemplateResponse("subscription_success.html", {"request": request, "message": _("Subscription successful!"), "session": session})
        except stripe.error.StripeError as e:
            raise HTTPException(status_code=400, detail=str(e))
    return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)

@app.get("/subscription/cancel", response_class=HTMLResponse)
async def subscription_cancel(request: Request):
    _ = request.state.gettext
    return templates.TemplateResponse("subscription_cancel.html", {"request": request, "message": _("Subscription process cancelled.")})

@app.post("/stripe-webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except stripe.error.SignatureVerificationError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        owner_id = session.metadata.get("owner_id")
        owner = db.query(models.Owner).filter(models.Owner.id == owner_id).first()
        if owner:
            customer_id = session.get("customer")
            subscription_id = session.get("subscription")

            owner.stripe_customer_id = customer_id
            owner.stripe_subscription_id = subscription_id
            owner.subscription_status = "premium"
            db.add(owner)

            subscription_obj = db.query(models.Subscription).filter(models.Subscription.stripe_subscription_id == subscription_id).first()
            if not subscription_obj:
                subscription_obj = models.Subscription(
                    owner_id=owner.id,
                    stripe_subscription_id=subscription_id,
                    status="active",
                    plan_id=settings.STRIPE_PREMIUM_PRICE_ID,
                    current_period_start=datetime.fromtimestamp(stripe.Subscription.retrieve(subscription_id).current_period_start),
                    current_period_end=datetime.fromtimestamp(stripe.Subscription.retrieve(subscription_id).current_period_end),
                )
                db.add(subscription_obj)
            else:
                subscription_obj.status = "active"
                subscription_obj.current_period_start = datetime.fromtimestamp(stripe.Subscription.retrieve(subscription_id).current_period_start)
                subscription_obj.current_period_end = datetime.fromtimestamp(stripe.Subscription.retrieve(subscription_id).current_period_end)
            db.commit()
            db.refresh(owner)
            if subscription_obj:
                db.refresh(subscription_obj)

    elif event["type"] == "customer.subscription.updated" or event["type"] == "customer.subscription.deleted":
        subscription_data = event["data"]["object"]
        subscription_id = subscription_data["id"]
        status = subscription_data["status"]

        subscription_obj = db.query(models.Subscription).filter(models.Subscription.stripe_subscription_id == subscription_id).first()
        if subscription_obj:
            subscription_obj.status = status
            subscription_obj.current_period_start = datetime.fromtimestamp(subscription_data["current_period_start"])
            subscription_obj.current_period_end = datetime.fromtimestamp(subscription_data["current_period_end"])
            db.commit()
            db.refresh(subscription_obj)

            owner = db.query(models.Owner).filter(models.Owner.id == subscription_obj.owner_id).first()
            if owner:
                if status == "active":
                    owner.subscription_status = "premium"
                else:
                    owner.subscription_status = "free"
                db.commit()
                db.refresh(owner)
    
    return Response(status_code=200)

@app.get("/subscription/manage", response_class=HTMLResponse)
async def manage_subscription(request: Request, db: Session = Depends(get_db), current_owner: Annotated[models.Owner, Depends(get_current_active_owner)]):
    _ = request.state.gettext
    customer_portal_url = None
    if current_owner.stripe_customer_id:
        try:
            portal_session = stripe.billing_portal.Session.create(
                customer=current_owner.stripe_customer_id,
                return_url=request.url_for("dashboard").__str__(),
            )
            customer_portal_url = portal_session.url
        except stripe.error.StripeError as e:
            print(f"Error creating customer portal session: {e}")
            customer_portal_url = None
    
    subscription = db.query(models.Subscription).filter(models.Subscription.owner_id == current_owner.id, models.Subscription.status == "active").first()
    subscription_status = schemas.SubscriptionStatus(
        status=current_owner.subscription_status,
        current_period_end=subscription.current_period_end if subscription else None,
        plan_id=subscription.plan_id if subscription else "free",
        is_premium=current_owner.subscription_status == "premium"
    )

    return templates.TemplateResponse(
        "subscription_manage.html",
        {
            "request": request,
            "owner": current_owner,
            "subscription_status": subscription_status,
            "customer_portal_url": customer_portal_url,
            "_": _
        }
    )

# Admin Panel
@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    _ = request.state.gettext
    return templates.TemplateResponse("admin_dashboard.html", {"request": request, "_": _})

@app.get("/admin/owners", response_class=HTMLResponse)
async def admin_list_owners(request: Request, db: Session = Depends(get_db)):
    _ = request.state.gettext
    owners = db.query(models.Owner).all()
    return templates.TemplateResponse("admin_owners.html", {"request": request, "owners": owners, "_": _})
