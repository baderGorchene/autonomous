from fastapi import FastAPI, Depends, HTTPException, status, Request, Form, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import func # Added for func.lower
from sqlalchemy.exc import IntegrityError
from datetime import timedelta, date, datetime, time
from typing import List, Optional, Dict, Any
import calendar
import uuid
import json

from . import models, schemas, security, notifications, availability_utils, analytics
from .database import SessionLocal, engine
from .config import settings
import stripe

import gettext
import os

models.Base.metadata.create_all(bind=engine)

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")

oauth2_scheme_owner = OAuth2PasswordBearer(tokenUrl="owner/token")
oauth2_scheme_customer = OAuth2PasswordBearer(tokenUrl="customer/token")
oauth2_scheme_admin = OAuth2PasswordBearer(tokenUrl="admin/token")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.middleware("http")
async def i18n_middleware(request: Request, call_next):
    lang_code = request.cookies.get("lang", "en")
    
    locale_dir = os.path.join(os.path.dirname(__file__), "..", "locales")
    if not os.path.exists(locale_dir):
        os.makedirs(locale_dir)

    try:
        translation = gettext.translation('messages', locale_dir, languages=[lang_code], fallback=True)
        translation.install()
    except Exception as e:
        print(f"Warning: Could not load translation for {lang_code}: {e}. Falling back to default.")
        translation = gettext.translation('messages', locale_dir, languages=['en'], fallback=True)
        translation.install()

    request.state.gettext = translation.gettext
    request.state.ngettext = translation.ngettext
    
    response = await call_next(request)
    return response

@app.get("/change_language/{lang_code}", response_class=RedirectResponse)
async def change_language(lang_code: str, request: Request):
    response = RedirectResponse(url=request.headers.get("referer", "/"), status_code=status.HTTP_302_FOUND)
    response.set_cookie(key="lang", value=lang_code, httponly=True, max_age=30*24*60*60)
    return response

async def get_current_owner(token: str = Depends(oauth2_scheme_owner), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    owner_email = security.verify_token(token, credentials_exception)
    owner = db.query(models.Owner).filter(models.Owner.email == owner_email).first()
    if owner is None:
        raise credentials_exception
    return owner

async def get_current_customer(token: str = Depends(oauth2_scheme_customer), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    customer_email = security.verify_token(token, credentials_exception)
    customer = db.query(models.Customer).filter(models.Customer.email == customer_email).first()
    if customer is None:
        raise credentials_exception
    return customer

async def get_current_admin(token: str = Depends(oauth2_scheme_admin), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authorized as admin",
        headers={"WWW-Authenticate": "Bearer"},
    )
    admin_email = security.verify_token(token, credentials_exception)
    if admin_email != "admin@example.com":
        raise credentials_exception
    return {"email": admin_email, "is_admin": True}


@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.post("/owner/signup", response_model=schemas.Owner)
async def owner_signup(owner: schemas.OwnerCreate, db: Session = Depends(get_db)):
    db_owner = db.query(models.Owner).filter(models.Owner.email == owner.email).first()
    if db_owner:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")
    
    hashed_password = security.get_password_hash(owner.password)
    db_owner = models.Owner(
        email=owner.email,
        hashed_password=hashed_password,
        name=owner.name,
        phone=owner.phone,
        subscription_status=models.SubscriptionStatus.FREE
    )
    db.add(db_owner)
    try:
        db.commit()
        db.refresh(db_owner)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")
    return db_owner

@app.post("/owner/token", response_model=schemas.Token)
async def owner_login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    owner = security.authenticate_owner(db, form_data.username, form_data.password)
    if not owner:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": owner.email, "scope": "owner"}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/owner/me", response_model=schemas.Owner)
async def read_owner_me(current_owner: models.Owner = Depends(get_current_owner)):
    return current_owner

@app.put("/owner/me", response_model=schemas.Owner)
async def update_owner_me(
    owner_update: schemas.OwnerUpdate,
    current_owner: models.Owner = Depends(get_current_owner),
    db: Session = Depends(get_db)
):
    update_data = owner_update.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(current_owner, key, value)
    
    db.add(current_owner)
    db.commit()
    db.refresh(current_owner)
    return current_owner

@app.post("/owner/services/", response_model=schemas.Service)
async def create_service_for_owner(
    service: schemas.ServiceCreate,
    current_owner: models.Owner = Depends(get_current_owner),
    db: Session = Depends(get_db)
):
    db_service = models.Service(**service.dict(), owner_id=current_owner.id)
    db.add(db_service)
    db.commit()
    db.refresh(db_service)
    return db_service

@app.get("/owner/services/", response_model=List[schemas.Service])
async def read_owner_services(
    current_owner: models.Owner = Depends(get_current_owner),
    db: Session = Depends(get_db)
):
    return db.query(models.Service).filter(models.Service.owner_id == current_owner.id).all()

@app.get("/owner/services/{service_id}", response_model=schemas.Service)
async def read_owner_service(
    service_id: int,
    current_owner: models.Owner = Depends(get_current_owner),
    db: Session = Depends(get_db)
):
    service = db.query(models.Service).filter(
        models.Service.id == service_id, models.Service.owner_id == current_owner.id
    ).first()
    if service is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")
    return service

@app.put("/owner/services/{service_id}", response_model=schemas.Service)
async def update_owner_service(
    service_id: int,
    service_update: schemas.ServiceUpdate,
    current_owner: models.Owner = Depends(get_current_owner),
    db: Session = Depends(get_db)
):
    service = db.query(models.Service).filter(
        models.Service.id == service_id, models.Service.owner_id == current_owner.id
    ).first()
    if service is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")
    
    update_data = service_update.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(service, key, value)
    
    db.add(service)
    db.commit()
    db.refresh(service)
    return service

@app.delete("/owner/services/{service_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_owner_service(
    service_id: int,
    current_owner: models.Owner = Depends(get_current_owner),
    db: Session = Depends(get_db)
):
    service = db.query(models.Service).filter(
        models.Service.id == service_id, models.Service.owner_id == current_owner.id
    ).first()
    if service is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")
    
    db.delete(service)
    db.commit()
    return

@app.post("/owner/availabilities/", response_model=schemas.Availability)
async def create_availability_for_owner(
    availability: schemas.AvailabilityCreate,
    current_owner: models.Owner = Depends(get_current_owner),
    db: Session = Depends(get_db)
):
    if availability.service_id:
        service = db.query(models.Service).filter(
            models.Service.id == availability.service_id,
            models.Service.owner_id == current_owner.id
        ).first()
        if not service:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found for this owner")

    db_availability = models.Availability(**availability.dict(), owner_id=current_owner.id)
    db.add(db_availability)
    db.commit()
    db.refresh(db_availability)
    return db_availability

@app.get("/owner/availabilities/", response_model=List[schemas.Availability])
async def read_owner_availabilities(
    current_owner: models.Owner = Depends(get_current_owner),
    db: Session = Depends(get_db)
):
    return db.query(models.Availability).filter(models.Availability.owner_id == current_owner.id).all()

@app.get("/owner/dashboard", response_class=HTMLResponse)
async def owner_dashboard(request: Request, current_owner: models.Owner = Depends(get_current_owner), db: Session = Depends(get_db)):
    _ = request.state.gettext
    
    upcoming_bookings = db.query(models.Booking).filter(
        models.Booking.owner_id == current_owner.id,
        models.Booking.date >= date.today()
    ).order_by(models.Booking.date, models.Booking.time).all()

    services = db.query(models.Service).filter(models.Service.owner_id == current_owner.id).all()

    monthly_bookings_data = analytics.get_monthly_bookings_data(db, current_owner.id)
    popular_services_data = analytics.get_popular_services_data(db, current_owner.id)

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "owner": current_owner,
            "bookings": upcoming_bookings,
            "services": services,
            "monthly_bookings_data": json.dumps(monthly_bookings_data),
            "popular_services_data": json.dumps(popular_services_data),
            "_": _,
            "current_lang": request.cookies.get("lang", "en"),
            "SubscriptionStatus": models.SubscriptionStatus
        }
    )

@app.get("/owner/api/analytics/monthly_bookings", response_model=List[schemas.MonthlyBookingData])
async def get_owner_monthly_bookings_api(
    current_owner: models.Owner = Depends(get_current_owner),
    db: Session = Depends(get_db)
):
    return analytics.get_monthly_bookings_data(db, current_owner.id)

@app.get("/owner/api/analytics/popular_services", response_model=List[schemas.PopularServiceData])
async def get_owner_popular_services_api(
    current_owner: models.Owner = Depends(get_current_owner),
    db: Session = Depends(get_db)
):
    return analytics.get_popular_services_data(db, current_owner.id)


@app.get("/bookslot.app/{owner_name_slug}", response_class=HTMLResponse)
async def public_booking_page(
    owner_name_slug: str,
    request: Request,
    db: Session = Depends(get_db)
):
    _ = request.state.gettext

    owner = db.query(models.Owner).filter(func.lower(models.Owner.name) == func.lower(owner_name_slug.replace('-', ' '))).first()
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Owner not found"))

    services = db.query(models.Service).filter(models.Service.owner_id == owner.id).all()
    
    customer_token = request.cookies.get("customer_access_token")
    customer_info = None
    if customer_token:
        try:
            customer_email = security.verify_token(customer_token, HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid customer token"))
            customer = db.query(models.Customer).filter(models.Customer.email == customer_email).first()
            if customer:
                customer_info = schemas.Customer.from_orm(customer)
        except Exception:
            pass

    return templates.TemplateResponse(
        "booking_page.html",
        {
            "request": request,
            "owner": owner,
            "services": services,
            "customer_info": customer_info,
            "_": _,
            "current_lang": request.cookies.get("lang", "en")
        }
    )

@app.get("/api/bookslot/{owner_id}/services/{service_id}/available_slots")
async def get_available_slots(
    owner_id: int,
    service_id: int,
    target_date: date,
    db: Session = Depends(get_db)
):
    owner = db.query(models.Owner).filter(models.Owner.id == owner_id).first()
    service = db.query(models.Service).filter(
        models.Service.id == service_id, models.Service.owner_id == owner_id
    ).first()

    if not owner or not service:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Owner or Service not found")

    available_times = availability_utils.get_available_slots_for_day(
        db, owner_id, service_id, target_date, service.duration_minutes
    )
    return {"available_slots": [t.isoformat() for t in available_times]}

@app.post("/api/bookslot/{owner_id}/book", response_model=schemas.Booking)
async def submit_booking(
    owner_id: int,
    booking_data: schemas.BookingCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    owner = db.query(models.Owner).filter(models.Owner.id == owner_id).first()
    service = db.query(models.Service).filter(
        models.Service.id == booking_data.service_id, models.Service.owner_id == owner_id
    ).first()

    if not owner or not service:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Owner or Service not found")

    available_slots = availability_utils.get_available_slots_for_day(
        db, owner_id, service.id, booking_data.date, service.duration_minutes
    )
    if booking_data.time not in available_slots:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Selected time slot is not available.")

    if booking_data.is_recurring:
        if not booking_data.recurrence_end_date or booking_data.recurrence_end_date < booking_data.date:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Recurrence end date is required and must be after the start date for recurring bookings.")
        
        recurrence_id = str(uuid.uuid4())
        current_date = booking_data.date
        created_bookings = []

        while current_date <= booking_data.recurrence_end_date:
            day_available_slots = availability_utils.get_available_slots_for_day(
                db, owner_id, service.id, current_date, service.duration_minutes
            )
            if booking_data.time in day_available_slots:
                db_booking = models.Booking(
                    owner_id=owner_id,
                    service_id=service.id,
                    customer_name=booking_data.customer_name,
                    customer_email=booking_data.customer_email,
                    customer_phone=booking_data.customer_phone,
                    date=current_date,
                    time=booking_data.time,
                    is_recurring=True,
                    recurrence_id=recurrence_id
                )
                db.add(db_booking)
                created_bookings.append(db_booking)
            current_date += timedelta(days=1)
        
        if not created_bookings:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No available slots found for the recurring booking series.")
        
        db.commit()
        for booking in created_bookings:
            db.refresh(booking)
            background_tasks.add_task(
                notifications.send_booking_confirmation_emails,
                owner, service, booking, is_recurring=True
            )
        return created_bookings[0]
    
    else:
        db_booking = models.Booking(
            owner_id=owner_id,
            service_id=service.id,
            customer_name=booking_data.customer_name,
            customer_email=booking_data.customer_email,
            customer_phone=booking_data.customer_phone,
            date=booking_data.date,
            time=booking_data.time,
            is_recurring=False
        )
        db.add(db_booking)
        db.commit()
        db.refresh(db_booking)

        background_tasks.add_task(notifications.send_booking_confirmation_emails, owner, service, db_booking)
        return db_booking

@app.get("/booking_confirmation", response_class=HTMLResponse)
async def booking_confirmation_page(request: Request):
    _ = request.state.gettext
    return templates.TemplateResponse(
        "booking_confirmation.html",
        {
            "request": request,
            "_": _,
            "current_lang": request.cookies.get("lang", "en")
        }
    )

@app.post("/customer/signup", response_model=schemas.Customer)
async def customer_signup(customer: schemas.CustomerCreate, db: Session = Depends(get_db)):
    db_customer = db.query(models.Customer).filter(models.Customer.email == customer.email).first()
    if db_customer:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")
    
    hashed_password = security.get_password_hash(customer.password)
    db_customer = models.Customer(
        email=customer.email,
        hashed_password=hashed_password,
        name=customer.name,
        phone=customer.phone
    )
    db.add(db_customer)
    try:
        db.commit()
        db.refresh(db_customer)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")
    return db_customer

@app.post("/customer/token", response_model=schemas.Token)
async def customer_login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    customer = security.authenticate_customer(db, form_data.username, form_data.password)
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": customer.email, "scope": "customer"}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/customer/me", response_model=schemas.Customer)
async def read_customer_me(current_customer: models.Customer = Depends(get_current_customer)):
    return current_customer

@app.put("/customer/me", response_model=schemas.Customer)
async def update_customer_me(
    customer_update: schemas.CustomerUpdate,
    current_customer: models.Customer = Depends(get_current_customer),
    db: Session = Depends(get_db)
):
    update_data = customer_update.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(current_customer, key, value)
    
    db.add(current_customer)
    db.commit()
    db.refresh(current_customer)
    return current_customer

@app.post("/reviews/", response_model=schemas.ReviewResponse, status_code=status.HTTP_201_CREATED)
async def submit_review(
    review_create: schemas.ReviewCreate,
    db: Session = Depends(get_db),
    current_customer: Optional[models.Customer] = Depends(get_current_customer)
):
    owner = db.query(models.Owner).filter(models.Owner.id == review_create.owner_id).first()
    service = db.query(models.Service).filter(
        models.Service.id == review_create.service_id,
        models.Service.owner_id == review_create.owner_id
    ).first()

    if not owner or not service:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Owner or Service not found.")

    customer_id = None
    customer_name = review_create.customer_name
    if current_customer:
        customer_id = current_customer.id
        customer_name = current_customer.name
    elif review_create.customer_id:
        existing_customer = db.query(models.Customer).filter(models.Customer.id == review_create.customer_id).first()
        if existing_customer:
            customer_id = existing_customer.id
            customer_name = existing_customer.name
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Provided customer_id does not exist.")
    
    if not customer_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Customer name is required for review.")

    db_review = models.Review(
        owner_id=review_create.owner_id,
        service_id=review_create.service_id,
        customer_id=customer_id,
        customer_name=customer_name,
        rating=review_create.rating,
        comment=review_create.comment
    )
    db.add(db_review)
    db.commit()
    db.refresh(db_review)
    return db_review

@app.get("/reviews/owner/{owner_id}", response_model=List[schemas.ReviewResponse])
async def get_reviews_for_owner(
    owner_id: int,
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100
):
    owner = db.query(models.Owner).filter(models.Owner.id == owner_id).first()
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Owner not found.")
    
    reviews = db.query(models.Review).filter(models.Review.owner_id == owner_id)
                .offset(skip).limit(limit).all()
    return reviews

@app.get("/reviews/service/{service_id}", response_model=List[schemas.ReviewResponse])
async def get_reviews_for_service(
    service_id: int,
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100
):
    service = db.query(models.Service).filter(models.Service.id == service_id).first()
    if not service:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found.")
    
    reviews = db.query(models.Review).filter(models.Review.service_id == service_id)
                .offset(skip).limit(limit).all()
    return reviews

stripe.api_key = settings.STRIPE_API_KEY

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
        customer_email = session.get('customer_details', {}).get('email')
        stripe_customer_id = session.get('customer')
        
        owner = db.query(models.Owner).filter(models.Owner.email == customer_email).first()
        
        if owner:
            line_items = stripe.checkout.Session.list_line_items(session['id'], limit=1).data
            if line_items and line_items[0].price.id == settings.STRIPE_PREMIUM_PRICE_ID:
                owner.subscription_status = models.SubscriptionStatus.PREMIUM
                owner.stripe_customer_id = stripe_customer_id
                db.add(owner)
                db.commit()
                db.refresh(owner)
                print(f"Owner {owner.email} upgraded to PREMIUM.")
            else:
                print(f"Checkout completed for {customer_email}, but not a premium subscription.")
        else:
            print(f"Owner not found for email: {customer_email}")

    elif event['type'] == 'customer.subscription.updated' or event['type'] == 'customer.subscription.deleted':
        subscription = event['data']['object']
        stripe_customer_id = subscription.get('customer')
        
        owner = db.query(models.Owner).filter(models.Owner.stripe_customer_id == stripe_customer_id).first()
        if owner:
            if event['type'] == 'customer.subscription.updated':
                if subscription['status'] == 'active':
                    owner.subscription_status = models.SubscriptionStatus.PREMIUM
                else:
                    owner.subscription_status = models.SubscriptionStatus.CANCELLED
                owner.stripe_subscription_id = subscription['id']
            elif event['type'] == 'customer.subscription.deleted':
                owner.subscription_status = models.SubscriptionStatus.FREE
                owner.stripe_subscription_id = None
            db.add(owner)
            db.commit()
            db.refresh(owner)
            print(f"Owner {owner.email} subscription status updated to {owner.subscription_status}.")
        else:
            print(f"Owner not found for Stripe customer ID: {stripe_customer_id}")

    return JSONResponse(status_code=200, content={"received": True})


@app.post("/owner/subscription/create-checkout-session", response_model=schemas.CheckoutSessionResponse)
async def create_checkout_session(
    current_owner: models.Owner = Depends(get_current_owner),
    db: Session = Depends(get_db)
):
    if current_owner.subscription_status == models.SubscriptionStatus.PREMIUM:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Owner already has a premium subscription.")

    try:
        if not current_owner.stripe_customer_id:
            stripe_customer = stripe.Customer.create(email=current_owner.email, name=current_owner.name)
            current_owner.stripe_customer_id = stripe_customer.id
            db.add(current_owner)
            db.commit()
            db.refresh(current_owner)
        
        checkout_session = stripe.checkout.Session.create(
            customer=current_owner.stripe_customer_id,
            payment_method_types=['card'],
            line_items=[
                {
                    'price': settings.STRIPE_PREMIUM_PRICE_ID,
                    'quantity': 1,
                },
            ],
            mode='subscription',
            success_url='https://example.com/success?session_id={CHECKOUT_SESSION_ID}',
            cancel_url='https://example.com/cancel',
            metadata={
                'owner_id': str(current_owner.id),
                'owner_email': current_owner.email
            }
        )
        return schemas.CheckoutSessionResponse(session_id=checkout_session.id, checkout_url=checkout_session.url)
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@app.get("/owner/subscription/manage")
async def manage_subscription(current_owner: models.Owner = Depends(get_current_owner)):
    if not current_owner.stripe_customer_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No Stripe customer ID found for this owner.")
    
    try:
        portalSession = stripe.billing_portal.Session.create(
            customer=current_owner.stripe_customer_id,
            return_url='https://example.com/owner/dashboard',
        )
        return RedirectResponse(url=portalSession.url)
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@app.get("/admin/dashboard", response_class=HTMLResponse)
async def admin_dashboard(request: Request, admin_user: dict = Depends(get_current_admin), db: Session = Depends(get_db)):
    _ = request.state.gettext
    owners = db.query(models.Owner).all()
    return templates.TemplateResponse(
        "admin_dashboard.html",
        {
            "request": request,
            "admin_user": admin_user,
            "owners": owners,
            "_": _,
            "current_lang": request.cookies.get("lang", "en")
        }
    )

@app.get("/admin/owners", response_model=List[schemas.Owner])
async def admin_list_owners(
    admin_user: dict = Depends(get_current_admin),
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100
):
    owners = db.query(models.Owner).offset(skip).limit(limit).all()
    return owners

@app.get("/admin/owners/{owner_id}", response_model=schemas.Owner)
async def admin_get_owner(
    owner_id: int,
    admin_user: dict = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    owner = db.query(models.Owner).filter(models.Owner.id == owner_id).first()
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Owner not found")
    return owner

@app.put("/admin/owners/{owner_id}", response_model=schemas.Owner)
async def admin_update_owner(
    owner_id: int,
    owner_update: schemas.AdminOwnerUpdate,
    admin_user: dict = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    owner = db.query(models.Owner).filter(models.Owner.id == owner_id).first()
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Owner not found")
    
    update_data = owner_update.dict(exclude_unset=True)
    for key, value in update_data.items():
        if key == "subscription_status" and value:
            owner.subscription_status = models.SubscriptionStatus[value.upper()]
        else:
            setattr(owner, key, value)
    
    db.add(owner)
    db.commit()
    db.refresh(owner)
    return owner

@app.delete("/admin/owners/{owner_id}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_delete_owner(
    owner_id: int,
    admin_user: dict = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    owner = db.query(models.Owner).filter(models.Owner.id == owner_id).first()
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Owner not found")
    
    db.delete(owner)
    db.commit()
    return

@app.get("/admin/owners/{owner_id}/services", response_model=List[schemas.Service])
async def admin_list_owner_services(
    owner_id: int,
    admin_user: dict = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    services = db.query(models.Service).filter(models.Service.owner_id == owner_id).all()
    return services

@app.put("/admin/services/{service_id}", response_model=schemas.Service)
async def admin_update_service(
    service_id: int,
    service_update: schemas.AdminServiceUpdate,
    admin_user: dict = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    service = db.query(models.Service).filter(models.Service.id == service_id).first()
    if not service:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")
    
    update_data = service_update.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(service, key, value)
    
    db.add(service)
    db.commit()
    db.refresh(service)
    return service

@app.delete("/admin/services/{service_id}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_delete_service(
    service_id: int,
    admin_user: dict = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    service = db.query(models.Service).filter(models.Service.id == service_id).first()
    if not service:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")
    
    db.delete(service)
    db.commit()
    return

@app.get("/admin/owners/{owner_id}/bookings", response_model=List[schemas.Booking])
async def admin_list_owner_bookings(
    owner_id: int,
    admin_user: dict = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    bookings = db.query(models.Booking).filter(models.Booking.owner_id == owner_id).all()
    return bookings

@app.put("/admin/bookings/{booking_id}", response_model=schemas.Booking)
async def admin_update_booking(
    booking_id: int,
    booking_update: schemas.AdminBookingUpdate,
    admin_user: dict = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    booking = db.query(models.Booking).filter(models.Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")
    
    update_data = booking_update.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(booking, key, value)
    
    db.add(booking)
    db.commit()
    db.refresh(booking)
    return booking

@app.delete("/admin/bookings/{booking_id}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_delete_booking(
    booking_id: int,
    admin_user: dict = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    booking = db.query(models.Booking).filter(models.Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")
    
    db.delete(booking)
    db.commit()
    return
