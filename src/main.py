from fastapi import FastAPI, Depends, HTTPException, status, Request, Response, Body, BackgroundTasks
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta, datetime, date
from typing import List, Optional
from jose import JWTError, jwt
from gettext import gettext as _
import locale as sys_locale
import os
import pytz

from . import models, schemas, security, notifications
from .config import settings
from .database import engine, SessionLocal
from .i18n import get_locale, activate_locale, load_translations
from .crud import (
    create_owner, get_owner_by_email, get_owner, update_owner_data,
    create_service, get_service, get_owner_services, update_service_data,
    create_availability, get_availability, get_service_availabilities, update_availability_data,
    create_booking, get_booking, get_owner_upcoming_bookings, is_time_slot_available,
    get_service_by_id_and_owner_id
)

import stripe

stripe.api_key = settings.STRIPE_SECRET_KEY

models.Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="BookSlot API",
    description="API for the BookSlot booking page service.",
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc"
)

load_translations(settings.LOCALES_DIR)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/token")

async def get_current_owner(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=_("Could not validate credentials"),
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
        token_data = schemas.TokenData(email=email)
    except JWTError:
        raise credentials_exception
    owner = get_owner_by_email(db, email=token_data.email)
    if owner is None:
        raise credentials_exception
    return owner

async def get_current_active_owner(current_owner: models.Owner = Depends(get_current_owner)):
    if not current_owner.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_("Inactive owner"))
    return current_owner

@app.get("/health", summary="Health check endpoint")
async def health_check():
    return {"status": "ok", "message": "BookSlot API is running!"}

@app.post("/api/register", response_model=schemas.OwnerResponse, summary="Register a new owner")
def register_owner(owner: schemas.OwnerCreate, db: Session = Depends(get_db)):
    db_owner = get_owner_by_email(db, email=owner.email)
    if db_owner:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_("Email already registered"))
    hashed_password = security.get_password_hash(owner.password)
    new_owner = create_owner(db=db, owner=owner, hashed_password=hashed_password)
    return new_owner

@app.post("/api/token", response_model=schemas.Token, summary="Get JWT token for owner login")
def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    owner = security.authenticate_owner(db, form_data.username, form_data.password)
    if not owner:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_("Incorrect email or password"),
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": owner.email}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/api/owner/me", response_model=schemas.OwnerResponse, summary="Get current owner's profile")
def read_owner_me(current_owner: models.Owner = Depends(get_current_active_owner)):
    return current_owner

@app.put("/api/owner/me", response_model=schemas.OwnerResponse, summary="Update current owner's profile")
def update_owner_me(
    owner_update: schemas.OwnerUpdate,
    current_owner: models.Owner = Depends(get_current_active_owner),
    db: Session = Depends(get_db)
):
    updated_owner = update_owner_data(db, current_owner, owner_update)
    if not updated_owner:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_("Failed to update owner profile"))
    return updated_owner

@app.post("/api/services", response_model=schemas.ServiceResponse, summary="Create a new service")
def create_service_for_owner(
    service: schemas.ServiceCreate,
    current_owner: models.Owner = Depends(get_current_active_owner),
    db: Session = Depends(get_db)
):
    return create_service(db=db, service=service, owner_id=current_owner.id)

@app.get("/api/services", response_model=List[schemas.ServiceResponse], summary="Get all services for the current owner")
def read_owner_services(
    current_owner: models.Owner = Depends(get_current_active_owner),
    db: Session = Depends(get_db)
):
    services = get_owner_services(db, owner_id=current_owner.id)
    return services

@app.get("/api/services/{service_id}", response_model=schemas.ServiceResponse, summary="Get a specific service by ID")
def read_service(
    service_id: int,
    current_owner: models.Owner = Depends(get_current_active_owner),
    db: Session = Depends(get_db)
):
    service = get_service_by_id_and_owner_id(db, service_id=service_id, owner_id=current_owner.id)
    if service is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Service not found"))
    return service

@app.put("/api/services/{service_id}", response_model=schemas.ServiceResponse, summary="Update a service")
def update_service_for_owner(
    service_id: int,
    service_update: schemas.ServiceUpdate,
    current_owner: models.Owner = Depends(get_current_active_owner),
    db: Session = Depends(get_db)
):
    service = get_service_by_id_and_owner_id(db, service_id=service_id, owner_id=current_owner.id)
    if service is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Service not found"))
    updated_service = update_service_data(db, service, service_update)
    return updated_service

@app.post("/api/services/{service_id}/availabilities", response_model=schemas.AvailabilityResponse, summary="Create availability for a service")
def create_availability_for_service(
    service_id: int,
    availability: schemas.AvailabilityCreate,
    current_owner: models.Owner = Depends(get_current_active_owner),
    db: Session = Depends(get_db)
):
    service = get_service_by_id_and_owner_id(db, service_id=service_id, owner_id=current_owner.id)
    if service is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Service not found"))
    return create_availability(db=db, availability=availability, service_id=service_id)

@app.get("/api/services/{service_id}/availabilities", response_model=List[schemas.AvailabilityResponse], summary="Get availabilities for a service")
def read_service_availabilities(
    service_id: int,
    current_owner: models.Owner = Depends(get_current_active_owner),
    db: Session = Depends(get_db)
):
    service = get_service_by_id_and_owner_id(db, service_id=service_id, owner_id=current_owner.id)
    if service is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Service not found"))
    availabilities = get_service_availabilities(db, service_id=service_id)
    return availabilities

@app.post("/api/book/{owner_name}", response_model=schemas.BookingResponse, summary="Submit a booking from the public page")
async def submit_booking(
    owner_name: str,
    booking: schemas.BookingCreate,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    owner = db.query(models.Owner).filter(models.Owner.name == owner_name).first()
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Booking page not found"))

    service = get_service_by_id_and_owner_id(db, service_id=booking.service_id, owner_id=owner.id)
    if not service:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Service not found for this owner"))

    if not is_time_slot_available(db, service_id=service.id, booking_time=booking.booking_time, duration_minutes=service.duration_minutes):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_("Selected time slot is not available"))

    if not owner.is_premium_subscriber:
        pass

    new_booking = create_booking(db=db, booking=booking, owner_id=owner.id, service_id=service.id)
    if not new_booking:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=_("Failed to create booking"))

    background_tasks.add_task(notifications.send_booking_confirmation_emails, new_booking, owner, service)
    background_tasks.add_task(notifications.send_whatsapp_notification_to_owner, new_booking, owner, service)

    return new_booking

@app.get("/api/owner/bookings", response_model=List[schemas.UpcomingBooking], summary="Get upcoming bookings for the current owner")
def read_owner_bookings(
    current_owner: models.Owner = Depends(get_current_active_owner),
    db: Session = Depends(get_db)
):
    bookings = get_owner_upcoming_bookings(db, owner_id=current_owner.id)
    return bookings

@app.middleware("http")
async def i18n_middleware(request: Request, call_next):
    lang = request.query_params.get("lang") or request.headers.get("Accept-Language", settings.DEFAULT_LOCALE).split(',')[0].split('-')[0]
    
    if not os.path.exists(os.path.join(settings.LOCALES_DIR, lang, 'LC_MESSAGES', 'messages.mo')):
        lang = settings.DEFAULT_LOCALE
        
    activate_locale(lang)
    sys_locale.setlocale(sys_locale.LC_ALL, f"{lang}_{lang.upper()}.UTF-8")

    response = await call_next(request)
    return response

@app.post("/api/owner/create-checkout-session", response_model=schemas.StripeCheckoutSessionResponse, summary="Create a Stripe Checkout Session for owner subscription")
async def create_checkout_session(
    current_owner: models.Owner = Depends(get_current_active_owner),
    db: Session = Depends(get_db)
):
    if current_owner.is_premium_subscriber:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_("Owner is already a premium subscriber."))

    try:
        prices = stripe.Price.list(lookup_keys=["bookslot_premium_monthly"], active=True)
        if prices.data:
            price_id = prices.data[0].id
        else:
            products = stripe.Product.list(ids=["prod_BookSlotPremium"])
            if not products.data:
                product = stripe.Product.create(
                    id="prod_BookSlotPremium",
                    name="BookSlot Premium Subscription",
                    description="Unlimited bookings for BookSlot service owners.",
                    metadata={"level": "premium"}
                )
                product_id = product.id
            else:
                product_id = products.data[0].id

            price = stripe.Price.create(
                unit_amount=1900,
                currency="usd",
                recurring={"interval": "month"},
                product=product_id,
                lookup_key="bookslot_premium_monthly"
            )
            price_id = price.id

        if not current_owner.stripe_customer_id:
            customer = stripe.Customer.create(
                email=current_owner.email,
                name=current_owner.name,
                metadata={"owner_id": current_owner.id}
            )
            current_owner.stripe_customer_id = customer.id
            db.add(current_owner)
            db.commit()
            db.refresh(current_owner)
        
        checkout_session = stripe.checkout.Session.create(
            customer=current_owner.stripe_customer_id,
            payment_method_types=["card"],
            line_items=[
                {
                    "price": price_id,
                    "quantity": 1,
                },
            ],
            mode="subscription",
            success_url=f"{settings.SERVER_NAME}/dashboard?payment=success&session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{settings.SERVER_NAME}/dashboard?payment=cancelled",
            client_reference_id=str(current_owner.id),
            metadata={"owner_id": current_owner.id}
        )
        return schemas.StripeCheckoutSessionResponse(
            session_id=checkout_session.id,
            session_url=checkout_session.url
        )
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=_("An unexpected error occurred during checkout session creation."))


@app.post("/stripe-webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except stripe.error.SignatureVerificationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        owner_id = session.get("client_reference_id")
        customer_id = session.get("customer")

        if owner_id and customer_id:
            db_owner = db.query(models.Owner).filter(models.Owner.id == int(owner_id)).first()
            if db_owner:
                db_owner.is_premium_subscriber = True
                db_owner.stripe_customer_id = customer_id
                db.add(db_owner)
                db.commit()
                db.refresh(db_owner)
                print(f"Owner {db_owner.email} is now a premium subscriber.")
            else:
                print(f"Owner with ID {owner_id} not found for completed session.")
        else:
            print("Missing owner_id or customer_id in checkout.session.completed event.")
            
    elif event["type"] == "customer.subscription.deleted":
        subscription = event["data"]["object"]
        customer_id = subscription.get("customer")
        if customer_id:
            db_owner = db.query(models.Owner).filter(models.Owner.stripe_customer_id == customer_id).first()
            if db_owner:
                db_owner.is_premium_subscriber = False
                db.add(db_owner)
                db.commit()
                db.refresh(db_owner)
                print(f"Owner {db_owner.email} subscription deleted.")
            else:
                print(f"Owner with Stripe Customer ID {customer_id} not found for subscription deleted event.")

    return Response(status_code=status.HTTP_200_OK)