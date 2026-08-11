from fastapi import FastAPI, Depends, HTTPException, status, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import List, Annotated, Optional, Dict, Any
from datetime import timedelta, date, datetime, time
from babel import dates, numbers
import stripe
import os
import logging

from . import models, schemas, crud, security, database, notifications, analytics, availability_utils
from .database import SessionLocal, engine, get_db
from .security import get_current_owner, create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES, get_password_hash, verify_password, get_current_customer, create_customer_access_token, CUSTOMER_ACCESS_TOKEN_EXPIRE_MINUTES
from .notifications import send_booking_confirmation_email, send_owner_booking_notification, send_customer_registration_email
from .i18n import get_locale, gettext as _, init_i18n, get_available_languages
from .logging_config import security_logger

models.Base.metadata.create_all(bind=engine)

app = FastAPI()

# Initialize i18n
init_i18n(app)

# Templates setup
templates = Jinja2Templates(directory="templates")

# OAuth2 for owner authentication
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="owner/token")

# OAuth2 for customer authentication
oauth2_customer_scheme = OAuth2PasswordBearer(tokenUrl="customer/token")

# Stripe configuration
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")

@app.middleware("http")
async def add_language_cookie(request: Request, call_next):
    if "lang" not in request.cookies:
        response = RedirectResponse(url=f"/?lang={get_locale(request)}")
        response.set_cookie(key="lang", value=get_locale(request), httponly=False, expires=3600*24*30)
        return response
    response = await call_next(request)
    return response

@app.get("/health", response_class=HTMLResponse)
async def health_check(request: Request):
    return "OK"

# --- Owner Authentication and Dashboard ---

@app.post("/owner/token", response_model=schemas.Token)
async def login_for_access_token(db: Annotated[Session, Depends(get_db)], form_data: Annotated[OAuth2PasswordRequestForm, Depends()]):
    owner = crud.authenticate_owner(db, form_data.username, form_data.password)
    if not owner:
        security_logger.warning(f"Failed owner login attempt for username: {form_data.username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_("Incorrect username or password"),
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": owner.email, "user_type": "owner"}, expires_delta=access_token_expires
    )
    security_logger.info(f"Owner {owner.email} logged in successfully.")
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/owner/register", response_model=schemas.OwnerOut)
def register_owner(owner: schemas.OwnerCreate, db: Session = Depends(get_db)):
    db_owner = crud.get_owner_by_email(db, email=owner.email)
    if db_owner:
        raise HTTPException(status_code=400, detail=_("Email already registered"))
    hashed_password = get_password_hash(owner.password)
    db_owner = models.Owner(email=owner.email, hashed_password=hashed_password, phone=owner.phone, name=owner.name)
    db.add(db_owner)
    db.commit()
    db.refresh(db_owner)
    security_logger.info(f"New owner registered: {owner.email}")
    return db_owner

@app.get("/owner/me", response_model=schemas.OwnerOut)
async def read_owners_me(current_owner: Annotated[models.Owner, Depends(get_current_owner)]):
    return current_owner

@app.get("/owner/dashboard", response_class=HTMLResponse)
async def owner_dashboard(request: Request, db: Annotated[Session, Depends(get_db)], current_owner: Annotated[models.Owner, Depends(get_current_owner)]):
    bookings = crud.get_owner_bookings(db, owner_id=current_owner.id)
    services = crud.get_owner_services(db, owner_id=current_owner.id)

    # Analytics data
    monthly_bookings_data = analytics.get_monthly_bookings_data(db, current_owner.id)
    popular_services_data = analytics.get_popular_services_data(db, current_owner.id)

    # Subscription status
    subscription = crud.get_owner_subscription(db, current_owner.id)
    is_premium = subscription and subscription.status == "active"

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "owner": current_owner,
            "bookings": bookings,
            "services": services,
            "current_locale": get_locale(request),
            "gettext": _,
            "dates": dates,
            "numbers": numbers,
            "monthly_bookings_data": monthly_bookings_data,
            "popular_services_data": popular_services_data,
            "is_premium": is_premium,
            "subscription": subscription
        },
    )

@app.post("/owner/profile", response_model=schemas.OwnerOut)
async def update_owner_profile(
    owner_update: schemas.OwnerUpdate,
    db: Annotated[Session, Depends(get_db)],
    current_owner: Annotated[models.Owner, Depends(get_current_owner)]
):
    try:
        updated_owner = crud.update_owner_profile(db, current_owner, owner_update)
        security_logger.info(f"Owner profile updated for {current_owner.email}")
        return updated_owner
    except Exception as e:
        security_logger.error(f"Error updating owner profile for {current_owner.email}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/owner/services", response_model=schemas.ServiceOut)
async def create_service(
    service: schemas.ServiceCreate,
    db: Annotated[Session, Depends(get_db)],
    current_owner: Annotated[models.Owner, Depends(get_current_owner)]
):
    db_service = models.Service(**service.model_dump(), owner_id=current_owner.id)
    db.add(db_service)
    db.commit()
    db.refresh(db_service)
    return db_service

@app.put("/owner/services/{service_id}", response_model=schemas.ServiceOut)
async def update_service(
    service_id: int,
    service_update: schemas.ServiceUpdate,
    db: Annotated[Session, Depends(get_db)],
    current_owner: Annotated[models.Owner, Depends(get_current_owner)]
):
    db_service = crud.get_service(db, service_id=service_id)
    if not db_service or db_service.owner_id != current_owner.id:
        raise HTTPException(status_code=404, detail=_("Service not found or not owned by current owner"))
    
    for key, value in service_update.model_dump(exclude_unset=True).items():
        setattr(db_service, key, value)
    db.commit()
    db.refresh(db_service)
    return db_service

@app.delete("/owner/services/{service_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_service(
    service_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_owner: Annotated[models.Owner, Depends(get_current_owner)]
):
    db_service = crud.get_service(db, service_id=service_id)
    if not db_service or db_service.owner_id != current_owner.id:
        raise HTTPException(status_code=404, detail=_("Service not found or not owned by current owner"))
    
    db.delete(db_service)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@app.post("/owner/availability", response_model=schemas.AvailabilityOut)
async def create_availability(
    availability: schemas.AvailabilityCreate,
    db: Annotated[Session, Depends(get_db)],
    current_owner: Annotated[models.Owner, Depends(get_current_owner)]
):
    db_availability = models.Availability(**availability.model_dump(), owner_id=current_owner.id)
    db.add(db_availability)
    db.commit()
    db.refresh(db_availability)
    return db_availability

@app.put("/owner/availability/{availability_id}", response_model=schemas.AvailabilityOut)
async def update_availability(
    availability_id: int,
    availability_update: schemas.AvailabilityUpdate,
    db: Annotated[Session, Depends(get_db)],
    current_owner: Annotated[models.Owner, Depends(get_current_owner)]
):
    db_availability = crud.get_availability(db, availability_id=availability_id)
    if not db_availability or db_availability.owner_id != current_owner.id:
        raise HTTPException(status_code=404, detail=_("Availability not found or not owned by current owner"))
    
    for key, value in availability_update.model_dump(exclude_unset=True).items():
        setattr(db_availability, key, value)
    db.commit()
    db.refresh(db_availability)
    return db_availability

@app.delete("/owner/availability/{availability_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_availability(
    availability_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_owner: Annotated[models.Owner, Depends(get_current_owner)]
):
    db_availability = crud.get_availability(db, availability_id=availability_id)
    if not db_availability or db_availability.owner_id != current_owner.id:
        raise HTTPException(status_code=404, detail=_("Availability not found or not owned by current owner"))
    
    db.delete(db_availability)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@app.get("/owner/analytics/monthly-bookings")
async def get_monthly_bookings(db: Annotated[Session, Depends(get_db)], current_owner: Annotated[models.Owner, Depends(get_current_owner)]):
    return analytics.get_monthly_bookings_data(db, current_owner.id)

@app.get("/owner/analytics/popular-services")
async def get_popular_services(db: Annotated[Session, Depends(get_db)], current_owner: Annotated[models.Owner, Depends(get_current_owner)]):
    return analytics.get_popular_services_data(db, current_owner.id)

@app.get("/owner/subscription", response_model=schemas.SubscriptionOut)
async def get_owner_subscription(
    db: Annotated[Session, Depends(get_db)],
    current_owner: Annotated[models.Owner, Depends(get_current_owner)]
):
    subscription = crud.get_owner_subscription(db, current_owner.id)
    if not subscription:
        raise HTTPException(status_code=404, detail=_("Subscription not found"))
    return subscription

# --- Public Booking Page ---

@app.get("/{owner_name}", response_class=HTMLResponse)
async def public_booking_page(request: Request, owner_name: str, db: Annotated[Session, Depends(get_db)]):
    owner = crud.get_owner_by_name(db, owner_name=owner_name)
    if not owner:
        raise HTTPException(status_code=404, detail=_("Owner not found"))
    services = crud.get_owner_services(db, owner_id=owner.id)
    
    # Get reviews for the owner
    reviews = crud.get_reviews_for_owner(db, owner_id=owner.id)

    return templates.TemplateResponse(
        "booking_page.html",
        {
            "request": request,
            "owner": owner,
            "services": services,
            "current_locale": get_locale(request),
            "gettext": _,
            "dates": dates,
            "available_languages": get_available_languages()
            ,
            "reviews": reviews
        },
    )

@app.get("/{owner_name}/available-slots")
async def get_slots(
    owner_name: str,
    service_id: int,
    selected_date: date,
    db: Annotated[Session, Depends(get_db)]
):
    owner = crud.get_owner_by_name(db, owner_name=owner_name)
    if not owner:
        raise HTTPException(status_code=404, detail=_("Owner not found"))
    service = crud.get_service(db, service_id=service_id)
    if not service or service.owner_id != owner.id:
        raise HTTPException(status_code=404, detail=_("Service not found for this owner"))

    available_slots = availability_utils.get_available_slots_for_day(
        db, owner.id, service.id, selected_date, service.duration_minutes
    )
    return {"available_slots": [s.isoformat() for s in available_slots]}

@app.post("/{owner_name}/book", response_class=HTMLResponse)
async def create_booking(
    request: Request,
    owner_name: str,
    booking_data: schemas.BookingCreate,
    db: Annotated[Session, Depends(get_db)]
):
    owner = crud.get_owner_by_name(db, owner_name=owner_name)
    if not owner:
        raise HTTPException(status_code=404, detail=_("Owner not found"))
    service = crud.get_service(db, service_id=booking_data.service_id)
    if not service or service.owner_id != owner.id:
        raise HTTPException(status_code=404, detail=_("Service not found for this owner"))

    # Basic availability check (more detailed check happens in availability_utils)
    available_slots = availability_utils.get_available_slots_for_day(
        db, owner.id, service.id, booking_data.date, service.duration_minutes
    )
    if booking_data.time not in available_slots:
        security_logger.warning(f"Attempt to book unavailable slot for owner {owner.email}, service {service.name} at {booking_data.date} {booking_data.time}")
        return templates.TemplateResponse(
            "booking_confirmation.html",
            {"request": request, "message": _("The selected time slot is no longer available. Please choose another time."), "success": False, "gettext": _}
        )
    
    try:
        db_booking = crud.create_booking(db=db, booking=booking_data, owner_id=owner.id)
        
        # Send notifications
        await send_booking_confirmation_email(owner, service, db_booking, booking_data.customer_email)
        await send_owner_booking_notification(owner, service, db_booking, booking_data.customer_name, booking_data.customer_email, booking_data.customer_phone)
        
        security_logger.info(f"New booking created for owner {owner.email} by {booking_data.customer_email} for service {service.name} at {booking_data.date} {booking_data.time}")
        return templates.TemplateResponse(
            "booking_confirmation.html",
            {"request": request, "message": _("Booking confirmed successfully!"), "success": True, "gettext": _}
        )
    except Exception as e:
        security_logger.error(f"Error creating booking for owner {owner.email}, service {service.name}: {e}")
        return templates.TemplateResponse(
            "booking_confirmation.html",
            {"request": request, "message": f"{_('An error occurred during booking:')} {e}", "success": False, "gettext": _}
        )

# --- Customer Authentication and Profile Management ---

@app.post("/customer/register", response_model=schemas.CustomerOut)
async def register_customer(customer: schemas.CustomerCreate, db: Session = Depends(get_db)):
    db_customer = crud.get_customer_by_email(db, email=customer.email)
    if db_customer:
        raise HTTPException(status_code=400, detail=_("Email already registered"))
    hashed_password = get_password_hash(customer.password)
    db_customer = models.Customer(email=customer.email, hashed_password=hashed_password, phone=customer.phone, name=customer.name)
    db.add(db_customer)
    db.commit()
    db.refresh(db_customer)
    await send_customer_registration_email(db_customer.email, db_customer.name)
    security_logger.info(f"New customer registered: {customer.email}")
    return db_customer

@app.post("/customer/token", response_model=schemas.Token)
async def customer_login_for_access_token(db: Annotated[Session, Depends(get_db)], form_data: Annotated[OAuth2PasswordRequestForm, Depends()]):
    customer = crud.authenticate_customer(db, form_data.username, form_data.password)
    if not customer:
        security_logger.warning(f"Failed customer login attempt for username: {form_data.username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_("Incorrect username or password"),
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=CUSTOMER_ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_customer_access_token(
        data={"sub": customer.email, "user_type": "customer"}, expires_delta=access_token_expires
    )
    security_logger.info(f"Customer {customer.email} logged in successfully.")
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/customer/me", response_model=schemas.CustomerOut)
async def read_customers_me(current_customer: Annotated[models.Customer, Depends(get_current_customer)]):
    return current_customer

@app.post("/customer/profile", response_model=schemas.CustomerOut)
async def update_customer_profile(
    customer_update: schemas.CustomerUpdate,
    db: Annotated[Session, Depends(get_db)],
    current_customer: Annotated[models.Customer, Depends(get_current_customer)]
):
    try:
        updated_customer = crud.update_customer_profile(db, current_customer, customer_update)
        security_logger.info(f"Customer profile updated for {current_customer.email}")
        return updated_customer
    except Exception as e:
        security_logger.error(f"Error updating customer profile for {current_customer.email}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# --- Reviews and Ratings ---

@app.post("/reviews", response_model=schemas.ReviewOut, status_code=status.HTTP_201_CREATED)
async def submit_review(
    review: schemas.ReviewCreate,
    db: Annotated[Session, Depends(get_db)],
    current_customer: Annotated[models.Customer, Depends(get_current_customer)]
):
    # Ensure the customer has a booking with the owner they are reviewing
    booking = db.query(models.Booking).filter(
        models.Booking.customer_id == current_customer.id,
        models.Booking.owner_id == review.owner_id
    ).first()

    if not booking:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_("You can only review businesses you have booked with."))

    db_review = crud.create_review(db, review, customer_id=current_customer.id)
    security_logger.info(f"Customer {current_customer.email} submitted a review for owner {review.owner_id}")
    return db_review

@app.get("/owners/{owner_id}/reviews", response_model=List[schemas.ReviewOut])
async def get_owner_reviews(owner_id: int, db: Annotated[Session, Depends(get_db)]):
    reviews = crud.get_reviews_for_owner(db, owner_id)
    return reviews


# --- Subscription Management (Stripe) ---

@app.post("/create-checkout-session")
async def create_checkout_session(db: Annotated[Session, Depends(get_db)], current_owner: Annotated[models.Owner, Depends(get_current_owner)]):
    try:
        # Check if owner already has an active subscription
        existing_subscription = crud.get_owner_subscription(db, current_owner.id)
        if existing_subscription and existing_subscription.status == "active":
            raise HTTPException(status_code=400, detail=_("You already have an active subscription."))

        checkout_session = stripe.checkout.Session.create(
            line_items=[
                {
                    "price": os.getenv("STRIPE_PREMIUM_PRICE_ID"), # Price ID from Stripe Dashboard
                    "quantity": 1,
                },
            ],
            mode="subscription",
            success_url=os.getenv("STRIPE_SUCCESS_URL") + "?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=os.getenv("STRIPE_CANCEL_URL"),
            client_reference_id=str(current_owner.id),
            customer_email=current_owner.email,
        )
        security_logger.info(f"Stripe checkout session created for owner {current_owner.email}")
        return {"id": checkout_session.id, "url": checkout_session.url}
    except Exception as e:
        security_logger.error(f"Error creating Stripe checkout session for owner {current_owner.email}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/stripe-webhook")
async def stripe_webhook(request: Request, db: Annotated[Session, Depends(get_db)]):
    payload = await request.body()
    sig_header = request.headers.get('stripe-signature')

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, WEBHOOK_SECRET
        )
    except ValueError as e:
        # Invalid payload
        security_logger.warning(f"Stripe webhook invalid payload: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except stripe.error.SignatureVerificationError as e:
        # Invalid signature
        security_logger.warning(f"Stripe webhook invalid signature: {e}")
        raise HTTPException(status_code=400, detail=str(e))

    # Handle the event
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        owner_id = session.get('client_reference_id')
        customer_email = session.get('customer_details', {}).get('email')
        subscription_id = session.get('subscription')

        if owner_id and subscription_id:
            crud.create_or_update_subscription(
                db,
                owner_id=int(owner_id),
                stripe_customer_id=session.get('customer'),
                stripe_subscription_id=subscription_id,
                status="active",
                current_period_end=datetime.fromtimestamp(session.get('expires_at') or session.get('current_period_end', 0))
            )
            security_logger.info(f"Stripe checkout session completed for owner {owner_id}, subscription {subscription_id}")
        else:
            security_logger.error(f"Stripe checkout.session.completed event missing owner_id or subscription_id. Session ID: {session.get('id')}")

    elif event['type'] == 'customer.subscription.updated':
        subscription = event['data']['object']
        # Update subscription status in your DB
        owner_id = crud.get_owner_id_by_stripe_customer_id(db, subscription.get('customer'))
        if owner_id:
            crud.create_or_update_subscription(
                db,
                owner_id=owner_id,
                stripe_customer_id=subscription.get('customer'),
                stripe_subscription_id=subscription.get('id'),
                status=subscription.get('status'),
                current_period_end=datetime.fromtimestamp(subscription.get('current_period_end', 0))
            )
            security_logger.info(f"Stripe subscription updated for owner {owner_id}, subscription {subscription.get('id')}. New status: {subscription.get('status')}")
        else:
            security_logger.error(f"Stripe customer.subscription.updated event could not find owner for customer ID: {subscription.get('customer')}")

    elif event['type'] == 'customer.subscription.deleted':
        subscription = event['data']['object']
        owner_id = crud.get_owner_id_by_stripe_customer_id(db, subscription.get('customer'))
        if owner_id:
            crud.create_or_update_subscription(
                db,
                owner_id=owner_id,
                stripe_customer_id=subscription.get('customer'),
                stripe_subscription_id=subscription.get('id'),
                status="cancelled", # Or 'inactive', depending on your model
                current_period_end=datetime.fromtimestamp(subscription.get('current_period_end', 0))
            )
            security_logger.info(f"Stripe subscription deleted for owner {owner_id}, subscription {subscription.get('id')}")
        else:
            security_logger.error(f"Stripe customer.subscription.deleted event could not find owner for customer ID: {subscription.get('customer')}")

    return {"status": "success"}

@app.get("/subscription-success", response_class=HTMLResponse)
async def subscription_success(request: Request, session_id: str, db: Annotated[Session, Depends(get_db)]):
    try:
        checkout_session = stripe.checkout.Session.retrieve(session_id)
        owner_id = checkout_session.client_reference_id
        subscription_id = checkout_session.subscription

        # Retrieve subscription details from Stripe
        stripe_subscription = stripe.Subscription.retrieve(subscription_id)
        current_period_end = datetime.fromtimestamp(stripe_subscription.current_period_end)

        if owner_id:
            crud.create_or_update_subscription(
                db,
                owner_id=int(owner_id),
                stripe_customer_id=checkout_session.customer,
                stripe_subscription_id=subscription_id,
                status="active",
                current_period_end=current_period_end
            )
            security_logger.info(f"Subscription success page accessed for owner {owner_id}, session {session_id}")
            return templates.TemplateResponse(
                "subscription_status.html",
                {"request": request, "message": _("Your subscription is now active!"), "success": True, "gettext": _}
            )
    except Exception as e:
        security_logger.error(f"Error processing subscription success for session {session_id}: {e}")
        pass # Fall through to generic error message

    return templates.TemplateResponse(
        "subscription_status.html",
        {"request": request, "message": _("There was an issue activating your subscription."), "success": False, "gettext": _}
    )

@app.get("/subscription-cancel", response_class=HTMLResponse)
async def subscription_cancel(request: Request):
    security_logger.info(f"Subscription cancel page accessed.")
    return templates.TemplateResponse(
        "subscription_status.html",
        {"request": request, "message": _("Your subscription was not activated."), "success": False, "gettext": _}
    )

# --- Admin Panel ---

@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    # This is a placeholder. In a real app, this would require admin authentication.
    return templates.TemplateResponse(
        "admin_dashboard.html",
        {"request": request, "gettext": _}
    )

@app.get("/admin/owners", response_model=List[schemas.OwnerOut])
async def get_all_owners(db: Annotated[Session, Depends(get_db)]):
    # Requires admin authentication
    owners = crud.get_all_owners(db)
    return owners

@app.get("/admin/owners/{owner_id}", response_model=schemas.OwnerOut)
async def get_owner_by_id(owner_id: int, db: Annotated[Session, Depends(get_db)]):
    owner = crud.get_owner(db, owner_id)
    if not owner:
        raise HTTPException(status_code=404, detail=_("Owner not found"))
    return owner

@app.put("/admin/owners/{owner_id}", response_model=schemas.OwnerOut)
async def update_owner_by_admin(owner_id: int, owner_update: schemas.OwnerUpdate, db: Annotated[Session, Depends(get_db)]):
    owner = crud.get_owner(db, owner_id)
    if not owner:
        raise HTTPException(status_code=404, detail=_("Owner not found"))
    updated_owner = crud.update_owner_profile(db, owner, owner_update)
    return updated_owner

@app.delete("/admin/owners/{owner_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_owner_by_admin(owner_id: int, db: Annotated[Session, Depends(get_db)]):
    owner = crud.get_owner(db, owner_id)
    if not owner:
        raise HTTPException(status_code=404, detail=_("Owner not found"))
    crud.delete_owner(db, owner_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@app.get("/admin/owners/{owner_id}/services", response_model=List[schemas.ServiceOut])
async def get_owner_services_admin(owner_id: int, db: Annotated[Session, Depends(get_db)]):
    services = crud.get_owner_services(db, owner_id)
    return services

@app.get("/admin/owners/{owner_id}/bookings", response_model=List[schemas.BookingOut])
async def get_owner_bookings_admin(owner_id: int, db: Annotated[Session, Depends(get_db)]):
    bookings = crud.get_owner_bookings(db, owner_id)
    return bookings
