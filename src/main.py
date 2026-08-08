import os
import stripe
from fastapi import FastAPI, Depends, HTTPException, status, Request, Response, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from sqlalchemy import extract, func
from datetime import datetime, timedelta, date
from typing import List, Annotated, Optional
import jwt
from jose import JWTError
import locale as sys_locale

from . import models, schemas, security, notifications, dependencies
from .config import settings
from .database import SessionLocal, engine
from .i18n import get_locale, activate_locale, translate as _t, format_currency_i18n
from .templates import templates

# Initialize Stripe
stripe.api_key = settings.STRIPE_SECRET_KEY
stripe.api_version = "2024-06-20" # Use a specific API version

models.Base.metadata.create_all(bind=engine)

app = FastAPI()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Dependency to get current owner
async def get_current_owner(token: Annotated[str, Depends(oauth2_scheme)], db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
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
    owner = security.get_owner_by_email(db, email=token_data.email)
    if owner is None:
        raise credentials_exception
    return owner

# Dependency to get current owner for templates (optional login)
async def get_current_owner_for_templates(
    request: Request,
    db: Session = Depends(get_db)
):
    token = request.cookies.get("access_token")
    if token:
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            email: str = payload.get("sub")
            if email:
                owner = security.get_owner_by_email(db, email=email)
                return owner
        except JWTError:
            pass # Invalid token, proceed as anonymous
    return None

# --- Root Endpoint ---
@app.get("/", response_class=HTMLResponse)
async def root(request: Request, db: Session = Depends(get_db)):
    activate_locale(request)
    owner = await get_current_owner_for_templates(request, db)
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "owner": owner, "gettext": _t, "locale": get_locale()}
    )

# --- Authentication Endpoints ---
@app.post("/token", response_model=schemas.Token)
async def login_for_access_token(
    response: Response,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Session = Depends(get_db)
):
    owner = security.authenticate_owner(db, form_data.username, form_data.password)
    if not owner:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": owner.email}, expires_delta=access_token_expires
    )
    response.set_cookie(key="access_token", value=access_token, httponly=True, expires=access_token_expires.total_seconds())
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/register", response_model=schemas.OwnerInDB)
def register_owner(owner: schemas.OwnerCreate, db: Session = Depends(get_db)):
    db_owner = security.get_owner_by_email(db, email=owner.email)
    if db_owner:
        raise HTTPException(status_code=400, detail="Email already registered")
    hashed_password = security.get_password_hash(owner.password)
    db_owner = models.Owner(
        email=owner.email,
        hashed_password=hashed_password,
        name=owner.name,
        phone=owner.phone,
        locale=owner.locale
    )
    db.add(db_owner)
    db.commit()
    db.refresh(db_owner)
    return db_owner

@app.get("/owners/me", response_model=schemas.OwnerInDB)
async def read_owners_me(current_owner: Annotated[models.Owner, Depends(get_current_owner)]):
    return current_owner

@app.post("/logout")
async def logout(response: Response):
    response.delete_cookie(key="access_token")
    return {"message": "Logged out successfully"}

@app.put("/owners/me", response_model=schemas.OwnerInDB)
async def update_owner_profile(
    owner_update: schemas.OwnerUpdate,
    current_owner: Annotated[models.Owner, Depends(get_current_owner)],
    db: Session = Depends(get_db)
):
    try:
        for field, value in owner_update.model_dump(exclude_unset=True).items():
            setattr(current_owner, field, value)
        db.add(current_owner)
        db.commit()
        db.refresh(current_owner)
        return current_owner
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# --- Service Management Endpoints ---
@app.post("/services/", response_model=schemas.ServiceInDB)
def create_service(
    service: schemas.ServiceCreate,
    current_owner: Annotated[models.Owner, Depends(get_current_owner)],
    db: Session = Depends(get_db)
):
    db_service = models.Service(**service.model_dump(), owner_id=current_owner.id)
    db.add(db_service)
    db.commit()
    db.refresh(db_service)
    return db_service

@app.get("/services/", response_model=List[schemas.ServiceInDB])
def get_services(
    current_owner: Annotated[models.Owner, Depends(get_current_owner)],
    db: Session = Depends(get_db)
):
    return db.query(models.Service).filter(models.Service.owner_id == current_owner.id).all()

# --- Availability Slot Management Endpoints ---
@app.post("/availability_slots/", response_model=schemas.AvailabilitySlotInDB)
def create_availability_slot(
    slot: schemas.AvailabilitySlotCreate,
    current_owner: Annotated[models.Owner, Depends(get_current_owner)],
    db: Session = Depends(get_db)
):
    service = db.query(models.Service).filter(
        models.Service.id == slot.service_id,
        models.Service.owner_id == current_owner.id
    ).first()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found or not owned by current owner")

    db_slot = models.AvailabilitySlot(**slot.model_dump())
    db.add(db_slot)
    db.commit()
    db.refresh(db_slot)
    return db_slot

@app.get("/availability_slots/{service_id}", response_model=List[schemas.AvailabilitySlotInDB])
def get_availability_slots(
    service_id: int,
    current_owner: Annotated[models.Owner, Depends(get_current_owner)],
    db: Session = Depends(get_db)
):
    slots = db.query(models.AvailabilitySlot).join(models.Service).filter(
        models.Service.id == service_id,
        models.Service.owner_id == current_owner.id
    ).all()
    if not slots:
        raise HTTPException(status_code=404, detail="Availability slots not found for this service or service not owned by current owner")
    return slots

# --- Public Booking Page Endpoints ---
@app.get("/book/{owner_name}", response_class=HTMLResponse)
async def get_booking_page(request: Request, owner_name: str, db: Session = Depends(get_db)):
    activate_locale(request)
    owner = db.query(models.Owner).filter(func.lower(models.Owner.name) == func.lower(owner_name)).first()
    if not owner:
        raise HTTPException(status_code=404, detail=_t("Owner not found"))

    services = db.query(models.Service).filter(models.Service.owner_id == owner.id).all()
    if not services:
        raise HTTPException(status_code=404, detail=_t("No services found for this owner"))

    service_data = []
    for service in services:
        availability_slots = db.query(models.AvailabilitySlot).filter(models.AvailabilitySlot.service_id == service.id).all()
        service_data.append({
            "id": service.id,
            "name": service.name,
            "description": service.description,
            "duration_minutes": service.duration_minutes,
            "price": format_currency_i18n(service.price, get_locale()),
            "availability": [
                {
                    "day_of_week": slot.day_of_week,
                    "start_time": slot.start_time,
                    "end_time": slot.end_time,
                }
                for slot in availability_slots
            ]
        })

    return templates.TemplateResponse(
        "booking_page.html",
        {"request": request, "owner": owner, "services": service_data, "gettext": _t, "locale": get_locale(), "settings": settings}
    )

@app.post("/book/{owner_name}", response_model=schemas.BookingConfirmation)
async def create_booking(
    request: Request,
    owner_name: str,
    booking_data: schemas.PublicBookingCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    activate_locale(request)
    owner = db.query(models.Owner).filter(func.lower(models.Owner.name) == func.lower(owner_name)).first()
    if not owner:
        raise HTTPException(status_code=404, detail=_t("Owner not found"))

    service = db.query(models.Service).filter(
        models.Service.id == booking_data.service_id,
        models.Service.owner_id == owner.id
    ).first()
    if not service:
        raise HTTPException(status_code=404, detail=_t("Service not found or not available for this owner"))

    # Validate booking time against availability slots
    booking_day_of_week = booking_data.booking_time.weekday() # Monday is 0, Sunday is 6
    booking_hour_minute = booking_data.booking_time.strftime("%H:%M")

    # Check for existing availability slot
    available_slot = db.query(models.AvailabilitySlot).filter(
        models.AvailabilitySlot.service_id == service.id,
        models.AvailabilitySlot.day_of_week == booking_day_of_week,
        models.AvailabilitySlot.start_time <= booking_hour_minute,
        models.AvailabilitySlot.end_time >= (booking_data.booking_time + timedelta(minutes=service.duration_minutes)).strftime("%H:%M")
    ).first()

    if not available_slot:
        raise HTTPException(status_code=400, detail=_t("Selected time is not available for this service."))

    # Check for overlapping bookings
    end_time_of_new_booking = booking_data.booking_time + timedelta(minutes=service.duration_minutes)
    overlapping_bookings = db.query(models.Booking).filter(
        models.Booking.service_id == service.id,
        models.Booking.booking_time < end_time_of_new_booking,
        (models.Booking.booking_time + service.duration_minutes * timedelta(minutes=1)) > booking_data.booking_time,
        models.Booking.status.in_(["pending", "confirmed", "paid"])
    ).all()


    if overlapping_bookings:
        raise HTTPException(status_code=400, detail=_t("This slot is already booked. Please choose another time."))

    try:
        db_booking = models.Booking(
            owner_id=owner.id,
            service_id=service.id,
            customer_name=booking_data.customer_name,
            customer_email=booking_data.customer_email,
            customer_phone=booking_data.customer_phone,
            booking_time=booking_data.booking_time,
            status="pending" # Default to pending, payment will change this
        )
        db.add(db_booking)
        db.commit()
        db.refresh(db_booking)

        booking_confirmation_data = schemas.BookingConfirmation(
            message=_t("Booking created successfully!"),
            booking_id=db_booking.id,
            owner_name=owner.name,
            service_name=service.name,
            booking_time=db_booking.booking_time,
            customer_name=db_booking.customer_name,
            customer_email=db_booking.customer_email,
            customer_phone=db_booking.customer_phone,
            service_price=service.price
        )

        # Send notifications in background
        background_tasks.add_task(
            notifications.send_booking_confirmation_emails,
            owner.email,
            db_booking.customer_email,
            owner.name,
            db_booking.customer_name,
            service.name,
            db_booking.booking_time,
            owner.locale
        )
        if owner.phone and settings.TWILIO_WHATSAPP_NUMBER:
            background_tasks.add_task(
                notifications.send_whatsapp_notification,
                owner.phone,
                owner.name,
                db_booking.customer_name,
                service.name,
                db_booking.booking_time,
                owner.locale
            )
        if db_booking.customer_phone and settings.TWILIO_WHATSAPP_NUMBER:
            background_tasks.add_task(
                notifications.send_whatsapp_notification,
                db_booking.customer_phone,
                db_booking.customer_name,
                owner.name,
                service.name,
                db_booking.booking_time,
                owner.locale,
                is_customer=True
            )

        return booking_confirmation_data
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@app.get("/booking_confirmation/{booking_id}", response_class=HTMLResponse)
async def booking_confirmation_page(request: Request, booking_id: int, db: Session = Depends(get_db)):
    activate_locale(request)
    booking = db.query(models.Booking).filter(models.Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail=_t("Booking not found"))

    owner = db.query(models.Owner).filter(models.Owner.id == booking.owner_id).first()
    service = db.query(models.Service).filter(models.Service.id == booking.service_id).first()

    if not owner or not service:
        raise HTTPException(status_code=404, detail=_t("Associated owner or service not found"))

    context = {
        "request": request,
        "booking": booking,
        "owner": owner,
        "service": service,
        "gettext": _t,
        "locale": get_locale(),
        "format_currency_i18n": format_currency_i18n,
        "settings": settings
    }
    return templates.TemplateResponse("booking_confirmation.html", context)


# --- Owner Dashboard Endpoints ---
@app.get("/dashboard", response_class=HTMLResponse)
async def get_owner_dashboard(request: Request, current_owner: Annotated[models.Owner, Depends(get_current_owner)], db: Session = Depends(get_db)):
    activate_locale(request, current_owner.locale)
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "owner": current_owner, "gettext": _t, "locale": get_locale(), "settings": settings}
    )

@app.get("/api/dashboard/bookings", response_model=List[schemas.DashboardBooking])
async def get_owner_bookings(
    current_owner: Annotated[models.Owner, Depends(get_current_owner)],
    db: Session = Depends(get_db)
):
    bookings = db.query(models.Booking, models.Service).join(models.Service).filter(
        models.Booking.owner_id == current_owner.id
    ).order_by(models.Booking.booking_time).all()

    dashboard_bookings = []
    for booking, service in bookings:
        dashboard_bookings.append(schemas.DashboardBooking(
            id=booking.id,
            customer_name=booking.customer_name,
            customer_email=booking.customer_email,
            customer_phone=booking.customer_phone,
            booking_time=booking.booking_time,
            service_name=service.name,
            service_duration=service.duration_minutes,
            status=booking.status
        ))
    return dashboard_bookings

@app.get("/api/dashboard/services", response_model=List[schemas.DashboardService])
async def get_owner_services_api(
    current_owner: Annotated[models.Owner, Depends(get_current_owner)],
    db: Session = Depends(get_db)
):
    services = db.query(models.Service).filter(models.Service.owner_id == current_owner.id).all()
    return [schemas.DashboardService.from_orm(service) for service in services]

@app.get("/api/dashboard/availability/{service_id}", response_model=List[schemas.DashboardAvailabilitySlot])
async def get_owner_availability_api(
    service_id: int,
    current_owner: Annotated[models.Owner, Depends(get_current_owner)],
    db: Session = Depends(get_db)
):
    # Ensure the service belongs to the current owner
    service = db.query(models.Service).filter(
        models.Service.id == service_id,
        models.Service.owner_id == current_owner.id
    ).first()
    if not service:
        raise HTTPException(status_code=404, detail=_t("Service not found or not owned by current owner"))

    availability_slots = db.query(models.AvailabilitySlot).filter(
        models.AvailabilitySlot.service_id == service_id
    ).all()
    return [schemas.DashboardAvailabilitySlot.from_orm(slot) for slot in availability_slots]


# --- Payment Gateway Endpoints (Stripe) ---
@app.post("/api/create-payment-intent", response_model=schemas.PaymentResponse)
async def create_payment_intent(
    payment_intent_create: schemas.PaymentIntentCreate,
    db: Session = Depends(get_db)
):
    booking = db.query(models.Booking).filter(models.Booking.id == payment_intent_create.booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail=_t("Booking not found"))

    # Check if a payment for this booking already exists and is succeeded
    if booking.payment:
        if booking.payment.status == "succeeded":
            raise HTTPException(status_code=400, detail=_t("Payment for this booking has already succeeded."))
        # If a payment intent exists but is not succeeded, we could potentially update it or create a new one.
        # For simplicity, if it exists and is not succeeded, we'll retrieve its client_secret to allow retries.
        try:
            existing_payment_intent = stripe.PaymentIntent.retrieve(booking.payment.stripe_payment_intent_id)
            if existing_payment_intent.status != "succeeded":
                return schemas.PaymentResponse(
                    client_secret=existing_payment_intent.client_secret,
                    publishable_key=settings.STRIPE_PUBLIC_KEY,
                    booking_id=booking.id
                )
        except stripe.error.StripeError as e:
            # If retrieving fails, maybe the ID is old/invalid, proceed to create a new one
            print(f"Error retrieving existing PaymentIntent: {e}")
            pass # Fall through to create new payment intent

    service = db.query(models.Service).filter(models.Service.id == booking.service_id).first()
    if not service:
        raise HTTPException(status_code=404, detail=_t("Associated service not found"))

    amount_in_cents = int(service.price * 100) # Stripe expects amount in cents

    try:
        payment_intent = stripe.PaymentIntent.create(
            amount=amount_in_cents,
            currency="usd", # TODO: Make dynamic based on owner/service settings
            metadata={"booking_id": str(booking.id)},
            automatic_payment_methods={"enabled": True},
        )
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Create or update a Payment record in our database
    if booking.payment:
        # Update existing payment record if it's not succeeded
        db_payment = booking.payment
        db_payment.stripe_payment_intent_id = payment_intent.id
        db_payment.amount = amount_in_cents
        db_payment.currency = payment_intent.currency
        db_payment.status = payment_intent.status
        db_payment.updated_at = datetime.utcnow()
    else:
        # Create a new Payment record
        db_payment = models.Payment(
            booking_id=booking.id,
            stripe_payment_intent_id=payment_intent.id,
            amount=amount_in_cents,
            currency=payment_intent.currency,
            status=payment_intent.status,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db.add(db_payment)

    db.commit()
    db.refresh(db_payment)

    return schemas.PaymentResponse(
        client_secret=payment_intent.client_secret,
        publishable_key=settings.STRIPE_PUBLIC_KEY,
        booking_id=booking.id
    )

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
    if event['type'] == 'payment_intent.succeeded':
        payment_intent = event['data']['object'] # contains a stripe.PaymentIntent
        print(f"Stripe Webhook: PaymentIntent succeeded for ID: {payment_intent['id']}")

        booking_id = payment_intent['metadata'].get('booking_id')
        if booking_id:
            booking = db.query(models.Booking).filter(models.Booking.id == int(booking_id)).first()
            if booking:
                booking.status = "paid"
                db.add(booking)
                db.commit()
                db.refresh(booking)

                # Update our local Payment record
                db_payment = db.query(models.Payment).filter(models.Payment.stripe_payment_intent_id == payment_intent['id']).first()
                if db_payment:
                    db_payment.status = "succeeded"
                    db.add(db_payment)
                    db.commit()
                    db.refresh(db_payment)
                else:
                    # If payment record doesn't exist (e.g., created directly by Stripe for some reason), create it
                    db_payment = models.Payment(
                        booking_id=booking.id,
                        stripe_payment_intent_id=payment_intent['id'],
                        amount=payment_intent['amount'],
                        currency=payment_intent['currency'],
                        status="succeeded",
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow()
                    )
                    db.add(db_payment)
                    db.commit()
                    db.refresh(db_payment)

                # TODO: Send a payment confirmation email/WhatsApp
                # background_tasks.add_task(notifications.send_payment_confirmation, booking)

    elif event['type'] == 'payment_intent.payment_failed':
        payment_intent = event['data']['object']
        print(f"Stripe Webhook: PaymentIntent failed for ID: {payment_intent['id']}")

        booking_id = payment_intent['metadata'].get('booking_id')
        if booking_id:
            booking = db.query(models.Booking).filter(models.Booking.id == int(booking_id)).first()
            if booking:
                booking.status = "payment_failed"
                db.add(booking)
                db.commit()
                db.refresh(booking)

                # Update our local Payment record
                db_payment = db.query(models.Payment).filter(models.Payment.stripe_payment_intent_id == payment_intent['id']).first()
                if db_payment:
                    db_payment.status = "failed"
                    db.add(db_payment)
                    db.commit()
                    db.refresh(db_payment)
                else:
                    db_payment = models.Payment(
                        booking_id=booking.id,
                        stripe_payment_intent_id=payment_intent['id'],
                        amount=payment_intent['amount'],
                        currency=payment_intent['currency'],
                        status="failed",
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow()
                    )
                    db.add(db_payment)
                    db.commit()
                    db.refresh(db_payment)

    # ... handle other event types as needed

    return Response(status_code=200)


# --- Error Handlers ---
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    activate_locale(request)
    if exc.status_code == 404:
        return templates.TemplateResponse(
            "404.html",
            {"request": request, "message": exc.detail, "gettext": _t, "locale": get_locale()},
            status_code=404
        )
    return templates.TemplateResponse(
        "error.html",
        {"request": request, "message": exc.detail, "gettext": _t, "locale": get_locale()},
        status_code=exc.status_code
    )

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    activate_locale(request)
    return templates.TemplateResponse(
        "error.html",
        {"request": request, "message": _t("An unexpected error occurred."), "gettext": _t, "locale": get_locale()},
        status_code=500
    )
