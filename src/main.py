from fastapi import FastAPI, Depends, HTTPException, status, Form, Response, Request, APIRouter
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy.orm import Session
from datetime import timedelta, date, datetime, time
from typing import List, Optional
import calendar # For displaying recurring booking days
import stripe

from . import models, schemas, security, notifications, analytics, availability_utils, i18n
from .database import engine, get_db
from .config import settings

models.Base.metadata.create_all(bind=engine)

app = FastAPI()

app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

templates = Jinja2Templates(directory="src/templates")

# Make settings available in templates
templates.env.globals['settings'] = settings

@app.middleware("http")
async def add_i18n_context(request: Request, call_next):
    lang = i18n.get_language(request)
    _ = i18n.get_translator(lang)
    request.state._ = _ # Make _ available in request state
    templates.env.globals['gettext'] = _
    templates.env.globals['_'] = _ # Also make it available directly for convenience
    templates.env.globals['current_language'] = lang
    response = await call_next(request)
    return response

@app.get("/set_language/{lang}", response_class=RedirectResponse)
async def set_language_route(request: Request, lang: str):
    i18n.set_language(request, lang)
    return RedirectResponse(url=request.headers.get("referer", "/"), status_code=status.HTTP_302_FOUND)

# Main router for API endpoints
api_router = APIRouter(prefix="/api")

@app.get("/", response_class=HTMLResponse)
async def root(request: Request, db: Session = Depends(get_db)):
    owner = None
    try:
        owner = await security.get_current_owner(request.cookies.get("access_token"), db)
    except HTTPException:
        pass # Not logged in, which is fine for root

    if owner:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/signup", response_class=HTMLResponse)
async def signup(request: Request, db: Session = Depends(get_db), email: str = Form(...), password: str = Form(...), name: str = Form(...), phone: Optional[str] = Form(None)):
    owner = db.query(models.Owner).filter(models.Owner.email == email).first()
    if owner:
        return templates.TemplateResponse("signup.html", {"request": request, "error": "Email already registered"})

    hashed_password = security.get_password_hash(password)
    db_owner = models.Owner(email=email, hashed_password=hashed_password, name=name, phone=phone)
    db.add(db_owner)
    db.commit()
    db.refresh(db_owner)

    # Automatically log in after signup
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": db_owner.email}, expires_delta=access_token_expires
    )
    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    response.set_cookie(key="access_token", value=access_token, httponly=True, expires=access_token_expires.total_seconds())
    return response

@app.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request):
    return templates.TemplateResponse("signup.html", {"request": request})

@app.post("/login", response_class=HTMLResponse)
async def login(request: Request, db: Session = Depends(get_db), form_data: OAuth2PasswordRequestForm = Depends()):
    owner = db.query(models.Owner).filter(models.Owner.email == form_data.username).first()
    if not owner or not security.verify_password(form_data.password, owner.hashed_password):
        return templates.TemplateResponse("login.html", {"request": request, "error": "Incorrect email or password"})

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": owner.email}, expires_delta=access_token_expires
    )
    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    response.set_cookie(key="access_token", value=access_token, httponly=True, expires=access_token_expires.total_seconds())
    return response

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/logout", response_class=RedirectResponse)
async def logout():
    response = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    response.delete_cookie(key="access_token")
    return response

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db), owner: models.Owner = Depends(security.get_current_owner)):
    today = date.today()

    # Fetch all upcoming individual bookings (non-recurring occurrences)
    # This includes one-off bookings and individual occurrences of recurring series (if they were generated as separate booking records)
    upcoming_individual_bookings = db.query(models.Booking).filter(
        models.Booking.owner_id == owner.id,
        models.Booking.date >= today,
        models.Booking.is_recurring == False # Exclude recurring series definitions from this list
    ).order_by(models.Booking.date, models.Booking.time).all()

    # Fetch recurring booking series definitions
    # These are the 'master' booking records that define a recurring schedule
    recurring_booking_series = db.query(models.Booking).filter(
        models.Booking.owner_id == owner.id,
        models.Booking.is_recurring == True,
        (models.Booking.recurrence_end_date >= today) | (models.Booking.recurrence_end_date.is_(None)) # Only active/future recurring series
    ).order_by(models.Booking.time).all()

    # Analytics data
    monthly_bookings = analytics.get_monthly_bookings_data(db, owner.id)
    popular_services = analytics.get_popular_services_data(db, owner.id)

    # Subscription status
    subscription = db.query(models.Subscription).filter(models.Subscription.owner_id == owner.id, models.Subscription.status == "active").first()
    is_premium = subscription is not None

    context = {
        "request": request,
        "owner": owner,
        "upcoming_individual_bookings": upcoming_individual_bookings,
        "recurring_booking_series": recurring_booking_series,
        "monthly_bookings": monthly_bookings,
        "popular_services": popular_services,
        "is_premium": is_premium,
        "subscription": subscription,
        "current_language": i18n.get_language(request)
    }
    return templates.TemplateResponse("dashboard.html", context)

@app.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request, db: Session = Depends(get_db), owner: models.Owner = Depends(security.get_current_owner)):
    return templates.TemplateResponse("profile.html", {"request": request, "owner": owner, "current_language": i18n.get_language(request)})

@app.post("/profile", response_class=HTMLResponse)
async def update_profile(
    request: Request,
    db: Session = Depends(get_db),
    owner: models.Owner = Depends(security.get_current_owner),
    name: str = Form(...),
    phone: Optional[str] = Form(None)
):
    try:
        owner.name = name
        owner.phone = phone
        db.commit()
        db.refresh(owner)
        return templates.TemplateResponse("profile.html", {"request": request, "owner": owner, "message": "Profile updated successfully!", "current_language": i18n.get_language(request)})
    except Exception as e:
        db.rollback()
        return templates.TemplateResponse("profile.html", {"request": request, "owner": owner, "error": f"Error updating profile: {e}", "current_language": i18n.get_language(request)})

@app.get("/booking/{owner_name_slug}/{service_name_slug}", response_class=HTMLResponse)
async def booking_page(
    request: Request,
    owner_name_slug: str,
    service_name_slug: str,
    db: Session = Depends(get_db)
):
    owner = db.query(models.Owner).filter(models.Owner.name == owner_name_slug).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")

    service = db.query(models.Service).filter(models.Service.owner_id == owner.id, models.Service.name == service_name_slug).first()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")

    # Generate available slots for today initially
    today = date.today()
    available_slots = availability_utils.get_available_slots_for_day(db, owner.id, service.id, today, service.duration_minutes)

    context = {
        "request": request,
        "owner": owner,
        "service": service,
        "available_slots": available_slots,
        "today": today.isoformat(),
        "current_language": i18n.get_language(request)
    }
    return templates.TemplateResponse("booking_page.html", context)

@app.post("/booking/{owner_id}/{service_id}", response_class=HTMLResponse)
async def submit_booking(
    request: Request,
    owner_id: int,
    service_id: int,
    db: Session = Depends(get_db),
    customer_name: str = Form(...),
    customer_email: EmailStr = Form(...),
    customer_phone: Optional[str] = Form(None),
    booking_date: date = Form(...),
    booking_time: time = Form(...),
    is_recurring: bool = Form(False),
    recurrence_type: Optional[schemas.RecurrenceTypeEnum] = Form(None),
    recurrence_value: Optional[str] = Form(None),
    recurrence_end_date: Optional[date] = Form(None)
):
    owner = db.query(models.Owner).filter(models.Owner.id == owner_id).first()
    service = db.query(models.Service).filter(models.Service.id == service_id).first()
    if not owner or not service:
        raise HTTPException(status_code=404, detail="Owner or Service not found")

    # Basic slot validation (more robust validation should happen at availability_utils)
    # For MVP, assume if a slot is presented, it's valid, but a final check is good.
    potential_slots = availability_utils.get_available_slots_for_day(db, owner_id, service_id, booking_date, service.duration_minutes)
    if booking_time not in potential_slots:
        # This should ideally be handled client-side or with a clearer error message.
        # For now, redirect with an error.
        context = {"request": request, "error": "Selected time slot is not available.", "owner": owner, "service": service, "current_language": i18n.get_language(request)}
        return templates.TemplateResponse("booking_page.html", context)

    try:
        db_booking = models.Booking(
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
        db.add(db_booking)
        db.commit()
        db.refresh(db_booking)

        booking_details = {
            "service_name": service.name,
            "date": booking_date,
            "time": booking_time,
            "customer_name": customer_name,
            "customer_email": customer_email,
            "customer_phone": customer_phone,
            "owner_name": owner.name
        }

        # Send notifications
        notifications.send_booking_confirmation_email(owner.email, customer_email, booking_details, is_owner_notification=True)
        notifications.send_booking_confirmation_email(owner.email, customer_email, booking_details, is_owner_notification=False)
        if owner.phone: # Assuming owner has a WhatsApp enabled phone
             notifications.send_booking_confirmation_whatsapp(owner.phone, customer_phone, booking_details, is_owner_notification=True)
        if customer_phone: # Assuming customer provided a WhatsApp enabled phone
            notifications.send_booking_confirmation_whatsapp(owner.phone, customer_phone, booking_details, is_owner_notification=False)

        return templates.TemplateResponse("booking_confirmation.html", {"request": request, "booking": db_booking, "owner": owner, "service": service, "current_language": i18n.get_language(request)})
    except Exception as e:
        db.rollback()
        print(f"Booking submission error: {e}")
        context = {"request": request, "error": f"Error submitting booking: {e}", "owner": owner, "service": service, "current_language": i18n.get_language(request)}
        return templates.TemplateResponse("booking_page.html", context)

# Analytics API Endpoints
@api_router.get("/analytics/monthly-bookings", response_model=List[dict])
async def get_monthly_bookings(db: Session = Depends(get_db), owner: models.Owner = Depends(security.get_current_owner)):
    return analytics.get_monthly_bookings_data(db, owner.id)

@api_router.get("/analytics/popular-services", response_model=List[dict])
async def get_popular_services(db: Session = Depends(get_db), owner: models.Owner = Depends(security.get_current_owner)):
    return analytics.get_popular_services_data(db, owner.id)

app.include_router(api_router)

# Stripe integration
@app.post("/create-checkout-session")
async def create_checkout_session(request: Request, db: Session = Depends(get_db), owner: models.Owner = Depends(security.get_current_owner)):
    try:
        checkout_session = stripe.checkout.Session.create(
            line_items=[
                {
                    'price': settings.STRIPE_PREMIUM_PRICE_ID,
                    'quantity': 1,
                },
            ],
            mode='subscription',
            success_url=request.url_for("dashboard") + "?success=true",
            cancel_url=request.url_for("dashboard") + "?canceled=true",
            client_reference_id=str(owner.id),
            customer_email=owner.email
        )
        return RedirectResponse(checkout_session.url, status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
        owner_id = int(session.get('client_reference_id'))
        customer_id = session.get('customer')
        subscription_id = session.get('subscription')
        price_id = session['line_items']['data'][0]['price']['id'] if session.get('line_items') else None

        owner = db.query(models.Owner).filter(models.Owner.id == owner_id).first()
        if owner:
            # Check if subscription already exists to prevent duplicates
            existing_sub = db.query(models.Subscription).filter(models.Subscription.stripe_subscription_id == subscription_id).first()
            if not existing_sub:
                db_subscription = models.Subscription(
                    owner_id=owner.id,
                    stripe_customer_id=customer_id,
                    stripe_subscription_id=subscription_id,
                    current_plan_id=price_id or settings.STRIPE_PREMIUM_PRICE_ID,
                    status="active",
                    start_date=datetime.fromtimestamp(session['created'])
                )
                db.add(db_subscription)
                db.commit()
                db.refresh(db_subscription)
                print(f"Subscription created for owner {owner.id}")
            else:
                # Update existing subscription if needed (e.g., plan change, reactivation)
                existing_sub.status = "active"
                existing_sub.current_plan_id = price_id or settings.STRIPE_PREMIUM_PRICE_ID
                db.commit()
                db.refresh(existing_sub)
                print(f"Subscription updated for owner {owner.id}")

    elif event['type'] == 'customer.subscription.deleted' or event['type'] == 'customer.subscription.updated':
        subscription_data = event['data']['object']
        subscription_id = subscription_data['id']
        status_str = subscription_data['status'] # 'canceled', 'active', 'past_due', etc.

        db_subscription = db.query(models.Subscription).filter(models.Subscription.stripe_subscription_id == subscription_id).first()
        if db_subscription:
            db_subscription.status = status_str
            db_subscription.end_date = datetime.utcnow() if status_str == 'canceled' else None
            db.commit()
            db.refresh(db_subscription)
            print(f"Subscription {subscription_id} status updated to {status_str}")

    return Response(status_code=200)
