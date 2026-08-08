import os
from datetime import datetime, timedelta
from typing import List, Optional, Dict
from gettext import gettext as _

from fastapi import FastAPI, Depends, HTTPException, status, Request, Response, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from sqlalchemy import func
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import JSONResponse
from pydantic import EmailStr

import stripe

from src import models, schemas, security, notifications
from src.database import SessionLocal, engine, init_db
from src.config import settings
from src.utils import generate_recurring_dates

app = FastAPI()

app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

@app.on_event("startup")
def on_startup():
    init_db()

templates = Jinja2Templates(directory=os.path.join(settings.PROJECT_ROOT, "templates"))

@app.middleware("http")
async def add_i18n_middleware(request: Request, call_next):
    lang = request.session.get("lang", settings.DEFAULT_LOCALE)
    request.state.lang = lang
    
    import gettext
    try:
        translation = gettext.translation('messages', localedir=settings.LOCALES_DIR, languages=[lang])
        _ = translation.gettext
    except Exception as e:
        print(f"Warning: Could not load translation for {lang}: {e}")
        _ = gettext.gettext

    request.state._ = _

    response = await call_next(request)
    return response

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/token")

async def get_current_owner(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    _ = Request.get_current().state._ # Access _ from current request context
    owner = security.get_owner_from_token(db, token)
    if owner is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_("Could not validate credentials"),
            headers={"WWW-Authenticate": "Bearer"},
        )
    return owner

async def get_current_admin_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    _ = Request.get_current().state._
    admin_user = security.get_admin_user_from_token(db, token)
    if admin_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_("Could not validate credentials"),
            headers={"WWW-Authenticate": "Bearer"},
        )
    return admin_user

@app.post("/token", response_model=schemas.Token)
async def login_for_access_token(request: Request, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    _ = request.state._
    owner = db.query(models.Owner).filter(models.Owner.email == form_data.username).first()
    if not owner or not security.verify_password(form_data.password, owner.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_("Incorrect username or password"),
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": owner.email}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/signup", response_model=schemas.OwnerInDB)
async def owner_signup(request: Request, owner: schemas.OwnerCreate, db: Session = Depends(get_db)):
    _ = request.state._
    db_owner = db.query(models.Owner).filter(models.Owner.email == owner.email).first()
    if db_owner:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_("Email already registered"))
    
    hashed_password = security.get_password_hash(owner.password)
    db_owner = models.Owner(email=owner.email, hashed_password=hashed_password, name=owner.name, phone=owner.phone, language=owner.language)
    db.add(db_owner)
    db.commit()
    db.refresh(db_owner)
    return db_owner

@app.get("/toggle_language/{lang_code}")
async def toggle_language(lang_code: str, request: Request, response: Response):
    request.session["lang"] = lang_code
    referer = request.headers.get("referer", "/")
    return RedirectResponse(url=referer, status_code=status.HTTP_302_FOUND)

@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.get("/book/{owner_name}", response_class=HTMLResponse)
async def booking_page(owner_name: str, request: Request, db: Session = Depends(get_db)):
    _ = request.state._
    owner = db.query(models.Owner).filter(models.Owner.name == owner_name).first()
    if not owner:
        return templates.TemplateResponse(
            "error.html", {"request": request, "message": _("Owner not found")}, status_code=status.HTTP_404_NOT_FOUND
        )
    services = db.query(models.Service).filter(models.Service.owner_id == owner.id).all()
    
    templates.env.globals['_'] = _
    templates.env.filters['currency'] = lambda value, currency_code: f"{currency_code} {value:,.2f}"
    
    return templates.TemplateResponse(
        "booking_page.html",
        {"request": request, "owner": owner, "services": services, "_": _},
    )

@app.post("/book/{owner_name}", response_class=HTMLResponse)
async def submit_booking(
    owner_name: str,
    request: Request,
    service_id: int = Form(...),
    customer_name: str = Form(...),
    customer_email: EmailStr = Form(...),
    customer_phone: Optional[str] = Form(None),
    start_time_str: str = Form(...),
    is_recurring: bool = Form(False),
    recurrence_pattern: Optional[str] = Form(None),
    recurrence_end_date_str: Optional[str] = Form(None),
    recurrence_end_count: Optional[int] = Form(None),
    db: Session = Depends(get_db)
):
    _ = request.state._
    owner = db.query(models.Owner).filter(models.Owner.name == owner_name).first()
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Owner not found"))

    service = db.query(models.Service).filter(models.Service.id == service_id, models.Service.owner_id == owner.id).first()
    if not service:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Service not found"))

    try:
        start_time = datetime.strptime(start_time_str, "%Y-%m-%dT%H:%M")
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_("Invalid start time format."))

    if start_time < datetime.now():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_("Cannot book in the past."))

    recurrence_end_date = None
    if recurrence_end_date_str:
        try:
            recurrence_end_date = datetime.strptime(recurrence_end_date_str, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_("Invalid recurrence end date format."))

    booking_data_list = []
    parent_booking_obj = None

    if is_recurring and recurrence_pattern:
        recurring_slots = generate_recurring_dates(
            start_time=start_time,
            duration_minutes=service.duration_minutes,
            recurrence_pattern=recurrence_pattern.upper(),
            recurrence_end_date=recurrence_end_date,
            recurrence_end_count=recurrence_end_count
        )
        
        if not recurring_slots:
             raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_("No valid recurring slots generated."))

        for i, (slot_start, slot_end) in enumerate(recurring_slots):
            # TODO: Implement actual availability check here.
            
            new_booking = models.Booking(
                owner_id=owner.id,
                service_id=service.id,
                customer_name=customer_name,
                customer_email=customer_email,
                customer_phone=customer_phone,
                start_time=slot_start,
                end_time=slot_end,
                is_recurring=True,
                recurrence_pattern=recurrence_pattern,
                recurrence_end_date=recurrence_end_date,
                recurrence_end_count=recurrence_end_count,
                parent_booking_id=None
            )
            db.add(new_booking)
            db.flush()

            if i == 0:
                parent_booking_obj = new_booking
            
            if parent_booking_obj:
                new_booking.parent_booking_id = parent_booking_obj.id
            
            booking_data_list.append(new_booking)

    else:
        end_time = start_time + timedelta(minutes=service.duration_minutes)
        # TODO: Implement actual availability check here.
        new_booking = models.Booking(
            owner_id=owner.id,
            service_id=service.id,
            customer_name=customer_name,
            customer_email=customer_email,
            customer_phone=customer_phone,
            start_time=start_time,
            end_time=end_time,
            is_recurring=False
        )
        db.add(new_booking)
        booking_data_list.append(new_booking)

    db.commit()

    if booking_data_list:
        first_booking = booking_data_list[0]
        notifications.send_booking_confirmation_email(owner, service, first_booking)
        notifications.send_booking_notification_to_owner(owner, service, first_booking)
        
    templates.env.globals['_'] = _
    return templates.TemplateResponse(
        "booking_confirmation.html",
        {"request": request, "owner_name": owner_name, "customer_name": customer_name, "_": _},
    )

@app.get("/dashboard", response_class=HTMLResponse)
async def owner_dashboard(request: Request, db: Session = Depends(get_db), current_owner: models.Owner = Depends(get_current_owner)):
    _ = request.state._
    upcoming_bookings_raw = db.query(models.Booking, models.Service)\
        .join(models.Service, models.Booking.service_id == models.Service.id)\
        .filter(models.Booking.owner_id == current_owner.id)\
        .filter(models.Booking.start_time >= datetime.now() - timedelta(hours=1)) \
        .order_by(models.Booking.start_time)\
        .all()
    
    upcoming_bookings = []
    for booking, service in upcoming_bookings_raw:
        upcoming_bookings.append(schemas.UpcomingBooking(
            id=booking.id,
            service_id=booking.service_id,
            customer_name=booking.customer_name,
            customer_email=booking.customer_email,
            customer_phone=booking.customer_phone,
            start_time=booking.start_time,
            end_time=booking.end_time,
            owner_id=booking.owner_id,
            status=booking.status,
            service_name=service.name,
            service_duration=service.duration_minutes,
            service_price=service.price,
            is_recurring=booking.is_recurring,
            recurrence_pattern=booking.recurrence_pattern,
            recurrence_end_date=booking.recurrence_end_date,
            recurrence_end_count=booking.recurrence_end_count,
            parent_booking_id=booking.parent_booking_id
        ))

    total_bookings_this_month = db.query(models.Booking).filter(
        models.Booking.owner_id == current_owner.id,
        models.Booking.start_time >= datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    ).count()

    popular_services_raw = db.query(models.Service.name, func.count(models.Booking.id).label("booking_count")) \
        .join(models.Booking, models.Service.id == models.Booking.service_id) \
        .filter(models.Service.owner_id == current_owner.id) \
        .group_by(models.Service.name) \
        .order_by(func.count(models.Booking.id).desc()) \
        .limit(5) \
        .all()
    
    popular_services = [{"name": name, "count": count} for name, count in popular_services_raw]
    
    analytics_data = schemas.AnalyticsData(
        total_bookings_this_month=total_bookings_this_month,
        popular_services=popular_services
    )

    templates.env.globals['_'] = _
    templates.env.filters['currency'] = lambda value, currency_code: f"{currency_code} {value:,.2f}"

    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "owner": current_owner, "upcoming_bookings": upcoming_bookings, "analytics": analytics_data, "_": _},
    )

@app.post("/dashboard/profile", response_class=HTMLResponse)
async def update_owner_profile(
    request: Request,
    name: str = Form(...),
    email: EmailStr = Form(...),
    phone: Optional[str] = Form(None),
    language: str = Form("en"),
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(get_current_owner)
):
    _ = request.state._
    try:
        current_owner.name = name
        current_owner.email = email
        current_owner.phone = phone
        current_owner.language = language
        db.commit()
        db.refresh(current_owner)
        request.session["lang"] = language
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        print(f"Error updating profile: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_("Error updating profile. Please try again."))

@app.get("/dashboard/services", response_class=HTMLResponse)
async def manage_services_page(request: Request, db: Session = Depends(get_db), current_owner: models.Owner = Depends(get_current_owner)):
    _ = request.state._
    services = db.query(models.Service).filter(models.Service.owner_id == current_owner.id).all()
    templates.env.globals['_'] = _
    return templates.TemplateResponse("services.html", {"request": request, "owner": current_owner, "services": services, "_": _})

@app.post("/dashboard/services", response_class=HTMLResponse)
async def add_service(
    request: Request,
    name: str = Form(...),
    description: Optional[str] = Form(None),
    duration_minutes: int = Form(...),
    price: float = Form(...),
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(get_current_owner)
):
    _ = request.state._
    try:
        new_service = models.Service(
            owner_id=current_owner.id,
            name=name,
            description=description,
            duration_minutes=duration_minutes,
            price=price
        )
        db.add(new_service)
        db.commit()
        db.refresh(new_service)
        return RedirectResponse(url="/dashboard/services", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        print(f"Error adding service: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_("Error adding service. Please try again."))

@app.get("/dashboard/subscription", response_class=HTMLResponse)
async def manage_subscription_page(request: Request, db: Session = Depends(get_db), current_owner: models.Owner = Depends(get_current_owner)):
    _ = request.state._
    subscription = db.query(models.Subscription).filter(models.Subscription.owner_id == current_owner.id).first()
    templates.env.globals['_'] = _
    return templates.TemplateResponse("subscription.html", {"request": request, "owner": current_owner, "subscription": subscription, "stripe_public_key": settings.STRIPE_PUBLIC_KEY, "_": _})

@app.post("/create-checkout-session")
async def create_checkout_session(request: Request, current_owner: models.Owner = Depends(get_current_owner)):
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
            success_url=f"{settings.SERVER_NAME}/dashboard/subscription?success=true",
            cancel_url=f"{settings.SERVER_NAME}/dashboard/subscription?canceled=true",
            customer_email=current_owner.email,
            client_reference_id=str(current_owner.id),
        )
        return JSONResponse({"id": checkout_session.id})
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@app.post("/stripe-webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    _ = Request.get_current().state._
    payload = await request.body()
    sig_header = request.headers.get('stripe-signature')

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except stripe.error.SignatureVerificationError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        owner_id = int(session['client_reference_id'])
        customer_email = session['customer_details']['email']
        subscription_id = session['subscription']

        owner = db.query(models.Owner).filter(models.Owner.id == owner_id).first()
        if owner and owner.email == customer_email:
            stripe_subscription = stripe.Subscription.retrieve(subscription_id)
            
            db_subscription = models.Subscription(
                owner_id=owner_id,
                stripe_customer_id=session['customer'],
                stripe_subscription_id=subscription_id,
                status=stripe_subscription.status,
                current_period_end=datetime.fromtimestamp(stripe_subscription.current_period_end)
            )
            db.add(db_subscription)
            db.commit()
            db.refresh(db_subscription)
            notifications.send_subscription_confirmation_email(owner, db_subscription)
            print(f"Subscription created for owner {owner_id}")
        else:
            print(f"Owner {owner_id} not found or email mismatch for subscription.")

    elif event['type'] == 'customer.subscription.updated':
        subscription_data = event['data']['object']
        db_subscription = db.query(models.Subscription).filter(
            models.Subscription.stripe_subscription_id == subscription_data.id
        ).first()

        if db_subscription:
            db_subscription.status = subscription_data.status
            db_subscription.current_period_end = datetime.fromtimestamp(subscription_data.current_period_end)
            db.commit()
            print(f"Subscription {subscription_data.id} updated to status {subscription_data.status}")

    elif event['type'] == 'customer.subscription.deleted':
        subscription_data = event['data']['object']
        db_subscription = db.query(models.Subscription).filter(
            models.Subscription.stripe_subscription_id == subscription_data.id
        ).first()

        if db_subscription:
            db_subscription.status = subscription_data.status
            db.commit()
            print(f"Subscription {subscription_data.id} deleted.")

    return JSONResponse(status_code=200, content={"status": "success"})

@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request, db: Session = Depends(get_db), admin_user: models.AdminUser = Depends(get_current_admin_user)):
    _ = request.state._
    owners = db.query(models.Owner).all()
    templates.env.globals['_'] = _
    return templates.TemplateResponse("admin_dashboard.html", {"request": request, "admin_user": admin_user, "owners": owners, "_": _})

@app.get("/")
async def root():
    return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
