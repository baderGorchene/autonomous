from fastapi import FastAPI, Depends, HTTPException, status, Request, Form, Response
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from datetime import datetime, date, time, timedelta
from typing import List, Optional
import stripe
import gettext
import os
import uuid

from . import models, schemas, security, notifications, analytics, availability_utils
from .database import get_db, Base, engine
from .config import settings

models.Base.metadata.create_all(bind=engine)

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")

LOCALE_DIR = "locales"
languages = ["en", "ar", "fr"]

def get_locale(request: Request):
    lang = request.query_params.get("lang") or request.cookies.get("lang")
    if lang not in languages:
        lang = "en"
    return lang

@app.middleware("http")
async def add_i18n_middleware(request: Request, call_next):
    lang = get_locale(request)
    
    try:
        current_translator = gettext.translation("messages", LOCALE_DIR, languages=[lang], fallback=True)
        request.state.gettext = current_translator.gettext
    except FileNotFoundError:
        request.state.gettext = gettext.translation("messages", LOCALE_DIR, languages=["en"], fallback=True).gettext

    response = await call_next(request)
    response.set_cookie(key="lang", value=lang, httponly=False, expires=3600 * 24 * 30)
    return response

@app.get("/health", response_class=HTMLResponse)
async def health_check(request: Request):
    _ = request.state.gettext
    return HTMLResponse(f"<h1>{_('Service is healthy')}!</h1>")

@app.on_event("startup")
async def startup_event():
    templates.env.globals['gettext'] = lambda s: gettext.gettext(s)
    templates.env.globals['_'] = lambda s: gettext.gettext(s)
    templates.env.globals['datetime'] = datetime
    templates.env.globals['date'] = date
    templates.env.globals['time'] = time
    templates.env.globals['timedelta'] = timedelta
    templates.env.globals['round'] = round
    templates.env.filters['format_currency'] = lambda value, currency_code, locale_code: f"{value:,.2f} {currency_code}"

@app.post("/owner/register", response_model=schemas.Owner)
def register_owner(owner: schemas.OwnerCreate, db: Session = Depends(get_db)):
    db_owner = db.query(models.Owner).filter(models.Owner.email == owner.email).first()
    if db_owner:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    hashed_password = security.hash_password(owner.password)
    db_owner = models.Owner(
        email=owner.email,
        name=owner.name,
        phone=owner.phone,
        hashed_password=hashed_password
    )
    db.add(db_owner)
    db.commit()
    db.refresh(db_owner)
    return db_owner

@app.post("/owner/token", response_model=schemas.Token)
def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    owner = db.query(models.Owner).filter(models.Owner.email == form_data.username).first()
    if not owner or not security.verify_password(form_data.password, owner.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": owner.email, "user_type": "owner"}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/owner/me", response_model=schemas.Owner)
def read_owner_me(current_owner: schemas.Owner = Depends(security.get_current_owner)):
    return current_owner

@app.put("/owner/me", response_model=schemas.Owner)
def update_owner_me(
    owner_update: schemas.OwnerUpdate,
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(security.get_current_owner)
):
    update_data = owner_update.model_dump(exclude_unset=True)
    if "password" in update_data and update_data["password"]:
        update_data["hashed_password"] = security.hash_password(update_data.pop("password"))
    if "email" in update_data and update_data["email"] != current_owner.email:
        existing_owner = db.query(models.Owner).filter(models.Owner.email == update_data["email"]).first()
        if existing_owner:
            raise HTTPException(status_code=400, detail="Email already registered by another owner")

    for key, value in update_data.items():
        setattr(current_owner, key, value)
    current_owner.updated_at = datetime.utcnow()
    db.add(current_owner)
    db.commit()
    db.refresh(current_owner)
    return current_owner

@app.post("/owner/services/", response_model=schemas.Service)
def create_service_for_owner(
    service: schemas.ServiceCreate,
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(security.get_current_owner)
):
    db_service = models.Service(**service.model_dump(), owner_id=current_owner.id)
    db.add(db_service)
    db.commit()
    db.refresh(db_service)
    return db_service

@app.get("/owner/services/", response_model=List[schemas.Service])
def read_owner_services(
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(security.get_current_owner)
):
    return db.query(models.Service).filter(models.Service.owner_id == current_owner.id).all()

@app.get("/owner/services/{service_id}", response_model=schemas.Service)
def read_owner_service(
    service_id: int,
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(security.get_current_owner)
):
    service = db.query(models.Service).filter(
        models.Service.id == service_id, models.Service.owner_id == current_owner.id
    ).first()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    return service

@app.put("/owner/services/{service_id}", response_model=schemas.Service)
def update_owner_service(
    service_id: int,
    service_update: schemas.ServiceUpdate,
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(security.get_current_owner)
):
    service = db.query(models.Service).filter(
        models.Service.id == service_id, models.Service.owner_id == current_owner.id
    ).first()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    
    update_data = service_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(service, key, value)
    db.add(service)
    db.commit()
    db.refresh(service)
    return service

@app.delete("/owner/services/{service_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_owner_service(
    service_id: int,
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(security.get_current_owner)
):
    service = db.query(models.Service).filter(
        models.Service.id == service_id, models.Service.owner_id == current_owner.id
    ).first()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    db.delete(service)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@app.post("/owner/availabilities/", response_model=schemas.Availability)
def create_availability_for_owner(
    availability: schemas.AvailabilityCreate,
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(security.get_current_owner)
):
    db_availability = models.Availability(**availability.model_dump(), owner_id=current_owner.id)
    if db_availability.date:
        db_availability.date = datetime.combine(db_availability.date, time.min)
    db_availability.start_time = datetime.combine(date.min, availability.start_time)
    db_availability.end_time = datetime.combine(date.min, availability.end_time)

    if availability.recurrence_type and availability.recurrence_start_date:
        db_availability.recurrence_start_date = datetime.combine(availability.recurrence_start_date, time.min)
        if availability.recurrence_end_date:
            db_availability.recurrence_end_date = datetime.combine(availability.recurrence_end_date, time.min)
    
    db.add(db_availability)
    db.commit()
    db.refresh(db_availability)
    return db_availability

@app.get("/owner/availabilities/", response_model=List[schemas.Availability])
def read_owner_availabilities(
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(security.get_current_owner)
):
    return db.query(models.Availability).filter(models.Availability.owner_id == current_owner.id).all()

@app.get("/book/{owner_name}", response_class=HTMLResponse)
async def booking_page(request: Request, owner_name: str, db: Session = Depends(get_db)):
    _ = request.state.gettext
    owner = db.query(models.Owner).filter(models.Owner.name == owner_name).first()
    if not owner:
        raise HTTPException(status_code=404, detail=_("Owner not found"))

    services = db.query(models.Service).filter(models.Service.owner_id == owner.id).all()
    
    return templates.TemplateResponse(
        "booking_page.html",
        {"request": request, "owner": owner, "services": services, "lang": get_locale(request), "_": _}
    )

@app.get("/api/book/{owner_name}/available_slots", response_model=List[time])
def get_available_slots_api(
    owner_name: str,
    service_id: int,
    target_date: date,
    db: Session = Depends(get_db)
):
    owner = db.query(models.Owner).filter(models.Owner.name == owner_name).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")
    
    service = db.query(models.Service).filter(
        models.Service.id == service_id, models.Service.owner_id == owner.id
    ).first()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found for this owner")

    available_slots = availability_utils.get_available_slots_for_day(
        db, owner.id, service.id, target_date, service.duration_minutes
    )
    return available_slots

@app.post("/book/{owner_name}/submit", response_class=HTMLResponse)
async def submit_booking(
    request: Request,
    owner_name: str,
    db: Session = Depends(get_db),
    service_id: int = Form(...),
    booking_date: date = Form(...),
    booking_time: time = Form(...),
    customer_name: str = Form(...),
    customer_email: EmailStr = Form(...),
    customer_phone: Optional[str] = Form(None),
    is_recurring: bool = Form(False)
):
    _ = request.state.gettext
    owner = db.query(models.Owner).filter(models.Owner.name == owner_name).first()
    if not owner:
        raise HTTPException(status_code=404, detail=_("Owner not found"))

    service = db.query(models.Service).filter(
        models.Service.id == service_id, models.Service.owner_id == owner.id
    ).first()
    if not service:
        raise HTTPException(status_code=404, detail=_("Service not found for this owner"))

    slot_start_dt = datetime.combine(booking_date, booking_time)
    slot_end_dt = slot_start_dt + timedelta(minutes=service.duration_minutes)

    existing_bookings = db.query(models.Booking).filter(
        models.Booking.owner_id == owner.id,
        models.Booking.service_id == service.id,
        models.Booking.date == booking_date,
        models.Booking.time == booking_time
    ).first()
    if existing_bookings:
        return templates.TemplateResponse(
            "booking_confirmation.html",
            {"request": request, "message": _("This slot is no longer available. Please choose another."), "success": False, "_": _},
            status_code=400
        )
    
    customer_account = db.query(models.Customer).filter(models.Customer.email == customer_email).first()
    customer_id_for_booking = customer_account.id if customer_account else None

    booking_recurrence_id = str(uuid.uuid4()) if is_recurring else None

    if is_recurring:
        db_booking = models.Booking(
            owner_id=owner.id,
            customer_id=customer_id_for_booking,
            service_id=service.id,
            date=booking_date,
            time=booking_time,
            customer_name=customer_name,
            customer_email=customer_email,
            customer_phone=customer_phone,
            is_confirmed=True,
            is_recurring=True,
            recurrence_id=booking_recurrence_id
        )
        db.add(db_booking)
        db.commit()
        db.refresh(db_booking)
    else:
        db_booking = models.Booking(
            owner_id=owner.id,
            customer_id=customer_id_for_booking,
            service_id=service.id,
            date=booking_date,
            time=booking_time,
            customer_name=customer_name,
            customer_email=customer_email,
            customer_phone=customer_phone,
            is_confirmed=True,
            is_recurring=False
        )
        db.add(db_booking)
        db.commit()
        db.refresh(db_booking)

    notifications.send_booking_confirmation_email(owner, service, db_booking, _=_)
    notifications.send_booking_confirmation_email_to_customer(owner, service, db_booking, _=_)
    if owner.phone:
        notifications.send_booking_confirmation_sms(owner, service, db_booking, _=_)

    return templates.TemplateResponse(
        "booking_confirmation.html",
        {"request": request, "message": _("Booking confirmed successfully!"), "success": True, "_": _}
    )

@app.get("/dashboard", response_class=HTMLResponse)
async def owner_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(security.get_current_owner)
):
    _ = request.state.gettext
    
    upcoming_bookings = db.query(models.Booking).filter(
        models.Booking.owner_id == current_owner.id,
        models.Booking.date >= date.today()
    ).order_by(models.Booking.date, models.Booking.time).all()

    services = db.query(models.Service).filter(models.Service.owner_id == current_owner.id).all()

    monthly_bookings = analytics.get_monthly_bookings_data(db, current_owner.id)
    popular_services = analytics.get_popular_services_data(db, current_owner.id)

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "owner": current_owner,
            "upcoming_bookings": upcoming_bookings,
            "services": services,
            "monthly_bookings": monthly_bookings,
            "popular_services": popular_services,
            "lang": get_locale(request),
            "_": _
        }
    )

@app.get("/owner/analytics/monthly-bookings", response_model=List[schemas.MonthlyBookingData])
def get_owner_monthly_bookings(
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(security.get_current_owner)
):
    return analytics.get_monthly_bookings_data(db, current_owner.id)

@app.get("/owner/analytics/popular-services", response_model=List[schemas.PopularServiceData])
def get_owner_popular_services(
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(security.get_current_owner)
):
    return analytics.get_popular_services_data(db, current_owner.id)

stripe.api_key = settings.STRIPE_API_KEY

@app.post("/create-checkout-session")
async def create_checkout_session(
    request: Request,
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(security.get_current_owner)
):
    _ = request.state.gettext
    if current_owner.subscription_status == models.SubscriptionStatus.PREMIUM:
        raise HTTPException(status_code=400, detail=_("You are already on a premium plan."))

    try:
        checkout_session = stripe.checkout.Session.create(
            line_items=[
                {
                    'price': settings.STRIPE_PREMIUM_PRICE_ID,
                    'quantity': 1,
                },
            ],
            mode='subscription',
            success_url=request.url_for('owner_dashboard')._url + "?checkout_success=true",
            cancel_url=request.url_for('owner_dashboard')._url + "?checkout_canceled=true",
            customer=current_owner.stripe_customer_id if current_owner.stripe_customer_id else None,
            client_reference_id=str(current_owner.id),
            metadata={
                "owner_id": current_owner.id
            }
        )
        return RedirectResponse(checkout_session.url, status_code=303)
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
        raise HTTPException(status_code=400, detail=str(e))
    except stripe.error.SignatureVerificationError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        owner_id = session.get('client_reference_id')
        if owner_id:
            owner = db.query(models.Owner).filter(models.Owner.id == int(owner_id)).first()
            if owner:
                owner.subscription_status = models.SubscriptionStatus.PREMIUM
                owner.stripe_customer_id = session.get('customer')
                owner.stripe_subscription_id = session.get('subscription')
                db.commit()
    elif event['type'] == 'customer.subscription.deleted':
        subscription = event['data']['object']
        stripe_customer_id = subscription.get('customer')
        owner = db.query(models.Owner).filter(models.Owner.stripe_customer_id == stripe_customer_id).first()
        if owner:
            owner.subscription_status = models.SubscriptionStatus.CANCELED
            owner.stripe_subscription_id = None
            db.commit()

    return JSONResponse(content={"status": "success"})

@app.get("/owner/subscription", response_class=HTMLResponse)
async def manage_subscription_page(
    request: Request,
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(security.get_current_owner)
):
    _ = request.state.gettext
    return templates.TemplateResponse(
        "subscription_management.html",
        {"request": request, "owner": current_owner, "_": _}
    )

@app.get("/admin/owners", response_model=List[schemas.Owner])
def admin_list_owners(db: Session = Depends(get_db)):
    return db.query(models.Owner).all()

@app.get("/admin/owners/{owner_id}", response_model=schemas.Owner)
def admin_get_owner(owner_id: int, db: Session = Depends(get_db)):
    owner = db.query(models.Owner).filter(models.Owner.id == owner_id).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")
    return owner

@app.put("/admin/owners/{owner_id}", response_model=schemas.Owner)
def admin_update_owner(owner_id: int, owner_update: schemas.OwnerUpdate, db: Session = Depends(get_db)):
    owner = db.query(models.Owner).filter(models.Owner.id == owner_id).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")
    
    update_data = owner_update.model_dump(exclude_unset=True)
    if "password" in update_data and update_data["password"]:
        update_data["hashed_password"] = security.hash_password(update_data.pop("password"))
    for key, value in update_data.items():
        setattr(owner, key, value)
    db.add(owner)
    db.commit()
    db.refresh(owner)
    return owner

@app.delete("/admin/owners/{owner_id}", status_code=status.HTTP_204_NO_CONTENT)
def admin_delete_owner(owner_id: int, db: Session = Depends(get_db)):
    owner = db.query(models.Owner).filter(models.Owner.id == owner_id).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")
    db.delete(owner)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@app.post("/customer/register", response_model=schemas.Customer)
def register_customer(customer: schemas.CustomerCreate, db: Session = Depends(get_db)):
    db_customer = db.query(models.Customer).filter(models.Customer.email == customer.email).first()
    if db_customer:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    hashed_password = security.hash_password(customer.password)
    db_customer = models.Customer(
        email=customer.email,
        name=customer.name,
        phone=customer.phone,
        hashed_password=hashed_password
    )
    db.add(db_customer)
    db.commit()
    db.refresh(db_customer)
    return db_customer

@app.post("/customer/token", response_model=schemas.Token)
def customer_login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    customer = db.query(models.Customer).filter(models.Customer.email == form_data.username).first()
    if not customer or not security.verify_password(form_data.password, customer.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": customer.email, "user_type": "customer"}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/customer/me", response_model=schemas.Customer)
def read_customer_me(current_customer: schemas.Customer = Depends(security.get_current_customer)):
    return current_customer

@app.put("/customer/me", response_model=schemas.Customer)
def update_customer_me(
    customer_update: schemas.CustomerUpdate,
    db: Session = Depends(get_db),
    current_customer: models.Customer = Depends(security.get_current_customer)
):
    update_data = customer_update.model_dump(exclude_unset=True)
    if "password" in update_data and update_data["password"]:
        update_data["hashed_password"] = security.hash_password(update_data.pop("password"))
    if "email" in update_data and update_data["email"] != current_customer.email:
        existing_customer = db.query(models.Customer).filter(models.Customer.email == update_data["email"]).first()
        if existing_customer:
            raise HTTPException(status_code=400, detail="Email already registered by another customer")

    for key, value in update_data.items():
        setattr(current_customer, key, value)
    current_customer.updated_at = datetime.utcnow()
    db.add(current_customer)
    db.commit()
    db.refresh(current_customer)
    return current_customer