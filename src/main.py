from fastapi import FastAPI, Depends, HTTPException, status, APIRouter, Request, Form, Response
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload
from datetime import timedelta, date, datetime, time
from typing import List, Optional, Dict, Any
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
import stripe
import json
import logging
from gettext import gettext as _
from gettext import translation
import os

from . import models, schemas, security, notifications, analytics, availability_utils
from .database import SessionLocal, engine, Base
from .config import settings

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="BookSlot API",
    description="API for BookSlot, a simple booking page for local service businesses.",
    version="0.1.0",
)

templates = Jinja2Templates(directory="templates")

stripe.api_key = settings.STRIPE_API_KEY

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

LOCALES_DIR = "locales"
DEFAULT_LOCALE = "en"
SUPPORTED_LOCALES = ["en", "ar", "fr"]

class LocaleMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        lang = request.cookies.get("locale", DEFAULT_LOCALE)
        if lang not in SUPPORTED_LOCALES:
            lang = DEFAULT_LOCALE

        request.state.locale = lang
        
        try:
            t = translation("messages", LOCALES_DIR, languages=[lang])
            t.install()
            request.state.gettext = t.gettext
            request.state._ = t.gettext 
        except Exception as e:
            logger.error(f"Error loading translation for {lang}: {e}")
            request.state.gettext = _ 
            request.state._ = _

        response = await call_next(request)
        return response

app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)
app.add_middleware(LocaleMiddleware)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="owners/token")

async def get_current_owner(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    owner = security.get_current_owner(db, token)
    if owner is None:
        raise credentials_exception
    return owner

oauth2_customer_scheme = OAuth2PasswordBearer(tokenUrl="customers/token")

async def get_current_customer(token: str = Depends(oauth2_customer_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    customer = security.get_current_customer(db, token)
    if customer is None:
        raise credentials_exception
    return customer


@app.get("/", response_class=HTMLResponse, summary="Root endpoint, redirects to dashboard if logged in")
async def root(request: Request, current_owner: Optional[models.Owner] = Depends(security.get_current_owner_optional), db: Session = Depends(get_db)):
    _ = request.state._
    if current_owner:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse("index.html", {"request": request, "current_owner": current_owner, "_": _})

@app.get("/health", summary="Health check endpoint")
async def health_check():
    return {"status": "ok"}

@app.get("/set-locale/{locale_code}", summary="Set user's preferred locale")
async def set_locale(locale_code: str, response: Response):
    if locale_code in SUPPORTED_LOCALES:
        response.set_cookie(key="locale", value=locale_code, httponly=True, max_age=30*24*60*60) 
        return {"message": f"Locale set to {locale_code}"}
    raise HTTPException(status_code=400, detail="Unsupported locale")


owner_router = APIRouter(prefix="/owners", tags=["Owners"])

@owner_router.post("/signup", response_model=schemas.OwnerResponse, summary="Register a new owner")
async def owner_signup(owner: schemas.OwnerCreate, db: Session = Depends(get_db)):
    db_owner = db.query(models.Owner).filter(models.Owner.email == owner.email).first()
    if db_owner:
        raise HTTPException(status_code=400, detail="Email already registered")
    hashed_password = security.get_password_hash(owner.password)
    db_owner = models.Owner(
        email=owner.email,
        hashed_password=hashed_password,
        name=owner.name,
        phone=owner.phone,
        currency=owner.currency,
        locale=owner.locale
    )
    db.add(db_owner)
    db.commit()
    db.refresh(db_owner)
    return db_owner

@owner_router.post("/token", response_model=schemas.Token, summary="Get JWT token for owner login")
async def owner_login_for_access_token(request: Request, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    _ = request.state._
    owner = security.authenticate_owner(db, form_data.username, form_data.password)
    if not owner:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_("Incorrect email or password"),
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": owner.email, "user_type": "owner"}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@owner_router.get("/me", response_model=schemas.OwnerResponse, summary="Get current owner's profile")
async def read_owner_me(current_owner: models.Owner = Depends(get_current_owner)):
    return current_owner

@owner_router.put("/me", response_model=schemas.OwnerResponse, summary="Update current owner's profile")
async def update_owner_me(
    owner_update: schemas.OwnerUpdate,
    current_owner: models.Owner = Depends(get_current_owner),
    db: Session = Depends(get_db)
):
    for field, value in owner_update.dict(exclude_unset=True).items():
        setattr(current_owner, field, value)
    db.add(current_owner)
    db.commit()
    db.refresh(current_owner)
    return current_owner


@owner_router.post("/services", response_model=schemas.ServiceResponse, summary="Create a new service")
async def create_service(
    service: schemas.ServiceCreate,
    current_owner: models.Owner = Depends(get_current_owner),
    db: Session = Depends(get_db)
):
    db_service = models.Service(**service.dict(), owner_id=current_owner.id)
    db.add(db_service)
    db.commit()
    db.refresh(db_service)
    return db_service

@owner_router.get("/services", response_model=List[schemas.ServiceResponse], summary="Get all services for the current owner")
async def get_owner_services(
    current_owner: models.Owner = Depends(get_current_owner),
    db: Session = Depends(get_db)
):
    services = db.query(models.Service).filter(models.Service.owner_id == current_owner.id).all()
    return services

@owner_router.get("/services/{service_id}", response_model=schemas.ServiceResponse, summary="Get a specific service by ID")
async def get_service_by_id(
    service_id: int,
    current_owner: models.Owner = Depends(get_current_owner),
    db: Session = Depends(get_db)
):
    service = db.query(models.Service).filter(
        models.Service.id == service_id,
        models.Service.owner_id == current_owner.id
    ).first()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    return service

@owner_router.put("/services/{service_id}", response_model=schemas.ServiceResponse, summary="Update a service")
async def update_service(
    service_id: int,
    service_update: schemas.ServiceUpdate,
    current_owner: models.Owner = Depends(get_current_owner),
    db: Session = Depends(get_db)
):
    service = db.query(models.Service).filter(
        models.Service.id == service_id,
        models.Service.owner_id == current_owner.id
    ).first()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    for field, value in service_update.dict(exclude_unset=True).items():
        setattr(service, field, value)
    db.add(service)
    db.commit()
    db.refresh(service)
    return service

@owner_router.delete("/services/{service_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a service")
async def delete_service(
    service_id: int,
    current_owner: models.Owner = Depends(get_current_owner),
    db: Session = Depends(get_db)
):
    service = db.query(models.Service).filter(
        models.Service.id == service_id,
        models.Service.owner_id == current_owner.id
    ).first()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    db.delete(service)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@owner_router.post("/availabilities", response_model=schemas.AvailabilityResponse, summary="Create new availability")
async def create_availability(
    availability: schemas.AvailabilityCreate,
    current_owner: models.Owner = Depends(get_current_owner),
    db: Session = Depends(get_db)
):
    db_availability = models.Availability(**availability.dict(), owner_id=current_owner.id)
    db.add(db_availability)
    db.commit()
    db.refresh(db_availability)
    return db_availability

@owner_router.get("/availabilities", response_model=List[schemas.AvailabilityResponse], summary="Get all availabilities for the current owner")
async def get_owner_availabilities(
    current_owner: models.Owner = Depends(get_current_owner),
    db: Session = Depends(get_db)
):
    availabilities = db.query(models.Availability).filter(models.Availability.owner_id == current_owner.id).all()
    return availabilities


@owner_router.get("/bookings", response_model=List[schemas.BookingResponse], summary="Get all upcoming bookings for the current owner")
async def get_owner_bookings(
    current_owner: models.Owner = Depends(get_current_owner),
    db: Session = Depends(get_db)
):
    bookings = db.query(models.Booking).filter(
        models.Booking.owner_id == current_owner.id,
        models.Booking.date >= date.today()
    ).order_by(models.Booking.date, models.Booking.time).all()
    return bookings

@owner_router.put("/bookings/{booking_id}/status", response_model=schemas.BookingResponse, summary="Update booking status")
async def update_booking_status(
    booking_id: int,
    status_update: schemas.BookingStatusUpdate,
    current_owner: models.Owner = Depends(get_current_owner),
    db: Session = Depends(get_db)
):
    booking = db.query(models.Booking).filter(
        models.Booking.id == booking_id,
        models.Booking.owner_id == current_owner.id
    ).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    booking.status = status_update.status
    db.add(booking)
    db.commit()
    db.refresh(booking)
    return booking


@owner_router.get("/analytics/monthly_bookings", response_model=List[schemas.MonthlyBookingsData], summary="Get monthly booking counts for the last 12 months")
async def get_owner_monthly_bookings(current_owner: models.Owner = Depends(get_current_owner), db: Session = Depends(get_db)):
    return analytics.get_monthly_bookings_data(db, current_owner.id)

@owner_router.get("/analytics/popular_services", response_model=List[schemas.PopularServiceData], summary="Get popular services by booking count")
async def get_owner_popular_services(current_owner: models.Owner = Depends(get_current_owner), db: Session = Depends(get_db)):
    return analytics.get_popular_services_data(db, current_owner.id)


@owner_router.post("/subscribe", summary="Create Stripe checkout session for subscription")
async def subscribe_to_premium(current_owner: models.Owner = Depends(get_current_owner)):
    if current_owner.is_premium and current_owner.stripe_subscription_id:
        raise HTTPException(status_code=400, detail="Owner is already subscribed to premium.")

    checkout_session = stripe.checkout.Session.create(
        customer=current_owner.stripe_customer_id if current_owner.stripe_customer_id else None,
        line_items=[
            {
                'price': settings.STRIPE_PREMIUM_PRICE_ID,
                'quantity': 1,
            },
        ],
        mode='subscription',
        success_url='http://localhost:8000/dashboard?success=true&session_id={CHECKOUT_SESSION_ID}',
        cancel_url='http://localhost:8000/dashboard?canceled=true',
        client_reference_id=str(current_owner.id),
    )
    return {"checkout_url": checkout_session.url}

@owner_router.get("/manage-subscription", summary="Redirect to Stripe customer portal to manage subscription")
async def manage_subscription(current_owner: models.Owner = Depends(get_current_owner)):
    if not current_owner.stripe_customer_id:
        raise HTTPException(status_code=400, detail="No Stripe customer ID found for this owner.")
    
    portal_session = stripe.billing_portal.Session.create(
        customer=current_owner.stripe_customer_id,
        return_url='http://localhost:8000/dashboard',
    )
    return {"portal_url": portal_session.url}

app.include_router(owner_router)


customer_router = APIRouter(prefix="/customers", tags=["Customers"])

@customer_router.post("/signup", response_model=schemas.CustomerResponse, summary="Register a new customer account")
async def customer_signup(customer: schemas.CustomerCreate, db: Session = Depends(get_db)):
    db_customer = db.query(models.Customer).filter(models.Customer.email == customer.email).first()
    if db_customer and db_customer.hashed_password: 
        raise HTTPException(status_code=400, detail="Email already registered with an account")
    
    hashed_password = security.get_password_hash(customer.password)
    
    if db_customer: 
        db_customer.hashed_password = hashed_password
        db_customer.name = customer.name
        db_customer.phone = customer.phone
    else: 
        db_customer = models.Customer(
            email=customer.email,
            hashed_password=hashed_password,
            name=customer.name,
            phone=customer.phone
        )
    db.add(db_customer)
    db.commit()
    db.refresh(db_customer)
    return db_customer

@customer_router.post("/token", response_model=schemas.Token, summary="Get JWT token for customer login")
async def customer_login_for_access_token(request: Request, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    _ = request.state._
    customer = security.authenticate_customer(db, form_data.username, form_data.password)
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_("Incorrect email or password"),
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": customer.email, "user_type": "customer"}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@customer_router.get("/me", response_model=schemas.CustomerResponse, summary="Get current customer's profile")
async def read_customer_me(current_customer: models.Customer = Depends(get_current_customer)):
    return current_customer

@customer_router.put("/me", response_model=schemas.CustomerResponse, summary="Update current customer's profile")
async def update_customer_me(
    customer_update: schemas.CustomerUpdate,
    current_customer: models.Customer = Depends(get_current_customer),
    db: Session = Depends(get_db)
):
    for field, value in customer_update.dict(exclude_unset=True).items():
        setattr(current_customer, field, value)
    db.add(current_customer)
    db.commit()
    db.refresh(current_customer)
    return current_customer

@customer_router.get("/{customer_id}/reviews", response_model=List[schemas.ReviewResponse], summary="Get all reviews submitted by a specific customer")
async def get_customer_reviews(
    customer_id: int,
    current_customer: models.Customer = Depends(get_current_customer), 
    db: Session = Depends(get_db)
):
    if customer_id != current_customer.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view other customer's reviews")
    
    reviews = db.query(models.Review).options(joinedload(models.Review.service)).filter(
        models.Review.customer_id == customer_id
    ).all()
    
    response_reviews = []
    for review in reviews:
        review_data = schemas.ReviewResponse.from_orm(review).dict()
        review_data["service_name"] = review.service.name if review.service else None
        response_reviews.append(review_data)
        
    return response_reviews


app.include_router(customer_router)


@app.get("/bookslot/{owner_name}", response_class=HTMLResponse, summary="Public booking page for an owner")
async def public_booking_page(request: Request, owner_name: str, db: Session = Depends(get_db)):
    _ = request.state._
    owner = db.query(models.Owner).filter(models.Owner.name == owner_name).first()
    if not owner:
        raise HTTPException(status_code=404, detail=_("Owner not found"))
    
    services = db.query(models.Service).filter(models.Service.owner_id == owner.id).all()
    
    selected_service_id = services[0].id if services else None

    return templates.TemplateResponse(
        "booking_page.html",
        {
            "request": request,
            "owner": owner,
            "services": services,
            "selected_service_id": selected_service_id,
            "today": date.today().isoformat(),
            "_": _
        }
    )

@app.get("/api/services/{service_id}/available_slots", summary="Get available slots for a service on a given date")
async def get_available_slots(
    service_id: int,
    target_date: date,
    db: Session = Depends(get_db)
):
    service = db.query(models.Service).filter(models.Service.id == service_id).first()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    
    owner = db.query(models.Owner).filter(models.Owner.id == service.owner_id).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found for this service")

    slots = availability_utils.get_available_slots_for_day(
        db, owner.id, service.id, target_date, service.duration_minutes
    )
    return [s.strftime("%H:%M") for s in slots]

@app.post("/book", response_class=HTMLResponse, summary="Submit a new booking")
async def submit_booking(
    request: Request,
    owner_id: int = Form(...),
    service_id: int = Form(...),
    customer_name: str = Form(...),
    customer_email: EmailStr = Form(...),
    customer_phone: Optional[str] = Form(None),
    booking_date: date = Form(...),
    booking_time: time = Form(...),
    is_recurring_booking: bool = Form(False),
    db: Session = Depends(get_db)
):
    _ = request.state._
    owner = db.query(models.Owner).filter(models.Owner.id == owner_id).first()
    service = db.query(models.Service).filter(models.Service.id == service_id).first()

    if not owner or not service:
        raise HTTPException(status_code=404, detail=_("Owner or service not found"))

    available_slots = availability_utils.get_available_slots_for_day(
        db, owner.id, service.id, booking_date, service.duration_minutes
    )
    if booking_time not in available_slots:
        raise HTTPException(status_code=400, detail=_("Selected time slot is no longer available. Please choose another."))

    customer = db.query(models.Customer).filter(models.Customer.email == customer_email).first()
    if not customer:
        customer = models.Customer(email=customer_email, name=customer_name, phone=customer_phone)
        db.add(customer)
        db.commit()
        db.refresh(customer)
    elif not customer.name: 
        customer.name = customer_name
        customer.phone = customer_phone
        db.add(customer)
        db.commit()
        db.refresh(customer)

    if is_recurring_booking:
        new_booking = models.Booking(
            owner_id=owner.id,
            service_id=service.id,
            customer_id=customer.id,
            customer_name=customer_name,
            customer_email=customer_email,
            customer_phone=customer_phone,
            date=booking_date,
            time=booking_time,
            status="confirmed",
            is_recurring_booking=True
        )
        db.add(new_booking)
        db.commit()
        db.refresh(new_booking)
    else:
        new_booking = models.Booking(
            owner_id=owner.id,
            service_id=service.id,
            customer_id=customer.id,
            customer_name=customer_name,
            customer_email=customer_email,
            customer_phone=customer_phone,
            date=booking_date,
            time=booking_time,
            status="confirmed",
            is_recurring_booking=False
        )
        db.add(new_booking)
        db.commit()
        db.refresh(new_booking)

    notifications.send_booking_confirmation_email(owner, service, new_booking, customer, request.state.locale)
    notifications.send_owner_notification(owner, service, new_booking, customer, request.state.locale)

    return templates.TemplateResponse(
        "booking_confirmation.html",
        {
            "request": request,
            "owner": owner,
            "service": service,
            "booking": new_booking,
            "customer_name": customer_name,
            "customer_email": customer_email,
            "_": _
        }
    )

@app.post("/services/{service_id}/reviews", response_model=schemas.ReviewResponse, status_code=status.HTTP_201_CREATED, summary="Submit a new review for a service")
async def submit_service_review(
    service_id: int,
    review_create: schemas.ReviewCreate,
    current_customer: models.Customer = Depends(get_current_customer), 
    db: Session = Depends(get_db)
):
    service = db.query(models.Service).filter(models.Service.id == service_id).first()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    
    db_review = models.Review(
        service_id=service_id,
        customer_id=current_customer.id,
        rating=review_create.rating,
        comment=review_create.comment
    )
    db.add(db_review)
    db.commit()
    db.refresh(db_review)
    
    response_review = schemas.ReviewResponse.from_orm(db_review).dict()
    response_review["customer_name"] = current_customer.name
    return response_review

@app.get("/services/{service_id}/reviews", response_model=List[schemas.ReviewResponse], summary="Get all reviews for a specific service")
async def get_service_reviews(
    service_id: int,
    db: Session = Depends(get_db)
):
    service = db.query(models.Service).filter(models.Service.id == service_id).first()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    
    reviews = db.query(models.Review).options(joinedload(models.Review.customer)).filter(
        models.Review.service_id == service_id
    ).order_by(models.Review.created_at.desc()).all()
    
    response_reviews = []
    for review in reviews:
        review_data = schemas.ReviewResponse.from_orm(review).dict()
        review_data["customer_name"] = review.customer.name if review.customer else "Anonymous"
        response_reviews.append(review_data)
        
    return response_reviews


admin_router = APIRouter(prefix="/admin", tags=["Admin"])

@admin_router.get("/owners", response_model=List[schemas.OwnerResponse], summary="Admin: List all owners")
async def admin_list_owners(db: Session = Depends(get_db)):
    owners = db.query(models.Owner).all()
    return owners

@admin_router.get("/owners/{owner_id}", response_model=schemas.OwnerResponse, summary="Admin: Get owner details by ID")
async def admin_get_owner(owner_id: int, db: Session = Depends(get_db)):
    owner = db.query(models.Owner).filter(models.Owner.id == owner_id).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")
    return owner

@admin_router.put("/owners/{owner_id}", response_model=schemas.OwnerResponse, summary="Admin: Update owner details")
async def admin_update_owner(owner_id: int, owner_update: schemas.OwnerUpdate, db: Session = Depends(get_db)):
    owner = db.query(models.Owner).filter(models.Owner.id == owner_id).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")
    for field, value in owner_update.dict(exclude_unset=True).items():
        setattr(owner, field, value)
    db.add(owner)
    db.commit()
    db.refresh(owner)
    return owner

@admin_router.delete("/owners/{owner_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Admin: Delete an owner")
async def admin_delete_owner(owner_id: int, db: Session = Depends(get_db)):
    owner = db.query(models.Owner).filter(models.Owner.id == owner_id).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")
    db.delete(owner)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

app.include_router(admin_router)


@app.post("/stripe-webhook", summary="Stripe webhook endpoint for subscription events")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
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

    event_type = event['type']
    data = event['data']
    object = data['object']

    if event_type == 'checkout.session.completed':
        session = object
        owner_id = session.get('client_reference_id')
        if owner_id:
            owner = db.query(models.Owner).filter(models.Owner.id == int(owner_id)).first()
            if owner:
                customer_id = session.get('customer')
                subscription_id = session.get('subscription')

                if customer_id and subscription_id:
                    owner.stripe_customer_id = customer_id
                    owner.stripe_subscription_id = subscription_id
                    owner.is_premium = True
                    owner.subscription_status = models.SubscriptionStatus.ACTIVE

                    db_subscription = db.query(models.Subscription).filter(
                        models.Subscription.stripe_subscription_id == subscription_id
                    ).first()
                    if not db_subscription:
                        db_subscription = models.Subscription(
                            owner_id=owner.id,
                            stripe_customer_id=customer_id,
                            stripe_subscription_id=subscription_id,
                            status=models.SubscriptionStatus.ACTIVE,
                            current_period_end=datetime.fromtimestamp(object['current_period_end'])
                        )
                        db.add(db_subscription)
                    else:
                        db_subscription.status = models.SubscriptionStatus.ACTIVE
                        db_subscription.current_period_end = datetime.fromtimestamp(object['current_period_end'])
                        db.add(db_subscription)
                    
                    db.commit()
                    db.refresh(owner)
                    db.refresh(db_subscription)
                    logger.info(f"Owner {owner.id} subscribed to premium.")
                else:
                    logger.warning(f"Checkout session completed for owner {owner_id} but missing customer_id or subscription_id.")
            else:
                logger.warning(f"Owner with ID {owner_id} not found for checkout.session.completed event.")
    
    elif event_type == 'customer.subscription.updated':
        subscription = object
        owner = db.query(models.Owner).filter(
            models.Owner.stripe_subscription_id == subscription['id']
        ).first()
        if owner:
            owner.subscription_status = models.SubscriptionStatus(subscription['status'])
            owner.is_premium = subscription['status'] == 'active' or subscription['status'] == 'trialing'
            db.add(owner)

            db_subscription = db.query(models.Subscription).filter(
                models.Subscription.stripe_subscription_id == subscription['id']
            ).first()
            if db_subscription:
                db_subscription.status = models.SubscriptionStatus(subscription['status'])
                db_subscription.current_period_end = datetime.fromtimestamp(subscription['current_period_end'])
                db.add(db_subscription)

            db.commit()
            db.refresh(owner)
            if db_subscription: db.refresh(db_subscription)
            logger.info(f"Subscription for owner {owner.id} updated to status: {subscription['status']}.")

    elif event_type == 'customer.subscription.deleted':
        subscription = object
        owner = db.query(models.Owner).filter(
            models.Owner.stripe_subscription_id == subscription['id']
        ).first()
        if owner:
            owner.subscription_status = models.SubscriptionStatus.CANCELED
            owner.is_premium = False
            db.add(owner)

            db_subscription = db.query(models.Subscription).filter(
                models.Subscription.stripe_subscription_id == subscription['id']
            ).first()
            if db_subscription:
                db_subscription.status = models.SubscriptionStatus.CANCELED
                db.add(db_subscription)

            db.commit()
            db.refresh(owner)
            if db_subscription: db.refresh(db_subscription)
            logger.info(f"Subscription for owner {owner.id} canceled.")
    
    return JSONResponse(content={"status": "success"})
