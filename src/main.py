import logging
from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import date, datetime, time, timedelta
from typing import List, Optional
import os
import secrets
from gettext import gettext as _
from gettext import ngettext

from . import models, schemas, crud, security, notifications, analytics, availability_utils, config
from .database import engine, get_db
from .config import settings
from .security import get_current_owner, get_current_customer, create_access_token, verify_password, hash_password
from .notifications import send_booking_confirmation_email, send_owner_notification_email, send_customer_welcome_email
from .schemas import OwnerCreate, OwnerLogin, ServiceCreate, ServiceUpdate, BookingCreate, OwnerProfileUpdate, CustomerCreate, CustomerLogin, CustomerProfileUpdate, ReviewCreate, ReviewUpdate, BookingRecurringCreate
from .models import Owner, Service, Booking, Customer, Review, Availability, RecurrenceType, Subscription, SubscriptionStatus
from .i18n import get_locale, setup_i18n_middleware
import pytz
import stripe

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bookslot_security.log"), # Log to a file
        logging.StreamHandler() # Also print to console
    ]
)
logger = logging.getLogger(__name__)

app = FastAPI()

# Setup i18n middleware
setup_i18n_middleware(app)

templates = Jinja2Templates(directory="templates")

# Stripe configuration
stripe.api_key = settings.STRIPE_SECRET_KEY

@app.on_event("startup")
def on_startup():
    models.Base.metadata.create_all(bind=engine)

@app.get("/health", status_code=status.HTTP_200_OK)
async def health_check():
    return {"status": "ok"}

@app.post("/token", response_model=schemas.Token)
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    owner = crud.get_owner_by_email(db, email=form_data.username)
    if not owner or not verify_password(form_data.password, owner.hashed_password):
        logger.warning(f"Failed login attempt for email: {form_data.username} from IP: {app.request.client.host if app.request else 'N/A'}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_("Incorrect username or password"),
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token(data={"sub": owner.email, "scope": "owner"})
    logger.info(f"Owner {owner.email} logged in successfully from IP: {app.request.client.host if app.request else 'N/A'}")
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/customer/token", response_model=schemas.Token)
async def login_for_customer_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    customer = crud.get_customer_by_email(db, email=form_data.username)
    if not customer or not verify_password(form_data.password, customer.hashed_password):
        logger.warning(f"Failed customer login attempt for email: {form_data.username} from IP: {app.request.client.host if app.request else 'N/A'}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_("Incorrect email or password"),
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token(data={"sub": customer.email, "scope": "customer"})
    logger.info(f"Customer {customer.email} logged in successfully from IP: {app.request.client.host if app.request else 'N/A'}")
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/owner/register", response_model=schemas.Owner)
async def register_owner(owner: schemas.OwnerCreate, request: Request, db: Session = Depends(get_db)):
    db_owner = crud.get_owner_by_email(db, email=owner.email)
    if db_owner:
        logger.warning(f"Registration attempt with existing email: {owner.email} from IP: {request.client.host}")
        raise HTTPException(status_code=400, detail=_("Email already registered"))
    try:
        new_owner = crud.create_owner(db=db, owner=owner)
        # notifications.send_welcome_email(new_owner.email, new_owner.name) # Optional
        logger.info(f"New owner registered: {new_owner.email} (ID: {new_owner.id}) from IP: {request.client.host}")
        return new_owner
    except Exception as e:
        logger.exception(f"Error during owner registration for email {owner.email}: {e}")
        raise HTTPException(status_code=500, detail=_("An unexpected error occurred during registration."))

@app.post("/customer/register", response_model=schemas.Customer)
async def register_customer(customer: schemas.CustomerCreate, request: Request, db: Session = Depends(get_db)):
    db_customer = crud.get_customer_by_email(db, email=customer.email)
    if db_customer:
        logger.warning(f"Customer registration attempt with existing email: {customer.email} from IP: {request.client.host}")
        raise HTTPException(status_code=400, detail=_("Email already registered"))
    try:
        new_customer = crud.create_customer(db=db, customer=customer)
        # notifications.send_customer_welcome_email(new_customer.email, new_customer.name) # Optional
        logger.info(f"New customer registered: {new_customer.email} (ID: {new_customer.id}) from IP: {request.client.host}")
        return new_customer
    except Exception as e:
        logger.exception(f"Error during customer registration for email {customer.email}: {e}")
        raise HTTPException(status_code=500, detail=_("An unexpected error occurred during registration."))

@app.get("/owner/dashboard", response_class=HTMLResponse)
async def owner_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    current_owner: schemas.Owner = Depends(get_current_owner)
):
    bookings = crud.get_owner_bookings(db, owner_id=current_owner.id)
    # Fetch services for the current owner
    services = crud.get_owner_services(db, owner_id=current_owner.id)

    # Analytics data
    monthly_bookings = analytics.get_monthly_bookings_data(db, current_owner.id)
    popular_services = analytics.get_popular_services_data(db, current_owner.id)

    # Subscription status
    subscription = crud.get_owner_subscription(db, current_owner.id)
    subscription_status = subscription.status.value if subscription else "none"
    
    # Reviews
    reviews = crud.get_reviews_for_owner(db, current_owner.id)

    # Adjust dates and times for display in owner's timezone
    owner_timezone = pytz.timezone(current_owner.timezone)
    adjusted_bookings = []
    for booking in bookings:
        booking_datetime_utc = datetime.combine(booking.date, booking.time).replace(tzinfo=pytz.utc)
        booking_datetime_owner_tz = booking_datetime_utc.astimezone(owner_timezone)
        adjusted_bookings.append({
            "id": booking.id,
            "customer_name": booking.customer_name,
            "customer_email": booking.customer_email,
            "customer_phone": booking.customer_phone,
            "service_name": booking.service.name,
            "date": booking_datetime_owner_tz.date(),
            "time": booking_datetime_owner_tz.time(),
            "status": booking.status.value,
            "is_recurring": booking.recurrence_type != RecurrenceType.NONE,
            "original_booking_id": booking.original_booking_id
        })

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "owner": current_owner,
            "bookings": adjusted_bookings,
            "services": services,
            "current_locale": get_locale(request),
            "_": _,
            "ngettext": ngettext,
            "monthly_bookings_data": monthly_bookings,
            "popular_services_data": popular_services,
            "subscription_status": subscription_status,
            "reviews": reviews
        }
    )

@app.get("/customer/profile", response_class=HTMLResponse)
async def customer_profile(
    request: Request,
    db: Session = Depends(get_db),
    current_customer: schemas.Customer = Depends(get_current_customer)
):
    bookings = crud.get_customer_bookings(db, current_customer.id)
    reviews = crud.get_reviews_by_customer(db, current_customer.id)

    return templates.TemplateResponse(
        "customer_dashboard.html", # Assuming a customer dashboard template
        {
            "request": request,
            "customer": current_customer,
            "bookings": bookings,
            "reviews": reviews,
            "current_locale": get_locale(request),
            "_": _,
            "ngettext": ngettext
        }
    )

@app.put("/owner/profile", response_model=schemas.Owner)
async def update_owner_profile(
    owner_update: schemas.OwnerProfileUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_owner: schemas.Owner = Depends(get_current_owner)
):
    try:
        updated_owner = crud.update_owner_profile(db, current_owner.id, owner_update)
        logger.info(f"Owner profile updated for {current_owner.email} by IP: {request.client.host}")
        return updated_owner
    except Exception as e:
        logger.exception(f"Error updating owner profile for {current_owner.email}: {e}")
        raise HTTPException(status_code=500, detail=_("An unexpected error occurred while updating profile."))

@app.put("/customer/profile", response_model=schemas.Customer)
async def update_customer_profile(
    customer_update: schemas.CustomerProfileUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_customer: schemas.Customer = Depends(get_current_customer)
):
    try:
        updated_customer = crud.update_customer_profile(db, current_customer.id, customer_update)
        logger.info(f"Customer profile updated for {current_customer.email} by IP: {request.client.host}")
        return updated_customer
    except Exception as e:
        logger.exception(f"Error updating customer profile for {current_customer.email}: {e}")
        raise HTTPException(status_code=500, detail=_("An unexpected error occurred while updating profile."))

@app.get("/owner/services", response_model=List[schemas.Service])
async def get_owner_services(
    db: Session = Depends(get_db),
    current_owner: schemas.Owner = Depends(get_current_owner)
):
    return crud.get_owner_services(db, owner_id=current_owner.id)

@app.post("/owner/services", response_model=schemas.Service)
async def create_owner_service(
    service: schemas.ServiceCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_owner: schemas.Owner = Depends(get_current_owner)
):
    try:
        new_service = crud.create_owner_service(db=db, service=service, owner_id=current_owner.id)
        logger.info(f"Service '{service.name}' created by owner {current_owner.email} (ID: {new_service.id}) from IP: {request.client.host}")
        return new_service
    except Exception as e:
        logger.exception(f"Error creating service for owner {current_owner.email}: {e}")
        raise HTTPException(status_code=500, detail=_("An unexpected error occurred while creating the service."))

@app.get("/owner/services/{service_id}", response_model=schemas.Service)
async def get_owner_service(
    service_id: int,
    db: Session = Depends(get_db),
    current_owner: schemas.Owner = Depends(get_current_owner)
):
    service = crud.get_service(db, service_id=service_id)
    if not service or service.owner_id != current_owner.id:
        logger.warning(f"Unauthorized access attempt to service_id: {service_id} by owner {current_owner.email} from IP: {app.request.client.host if app.request else 'N/A'}")
        raise HTTPException(status_code=404, detail=_("Service not found"))
    return service

@app.put("/owner/services/{service_id}", response_model=schemas.Service)
async def update_owner_service(
    service_id: int,
    service_update: schemas.ServiceUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_owner: schemas.Owner = Depends(get_current_owner)
):
    db_service = crud.get_service(db, service_id=service_id)
    if not db_service or db_service.owner_id != current_owner.id:
        logger.warning(f"Unauthorized update attempt to service_id: {service_id} by owner {current_owner.email} from IP: {request.client.host}")
        raise HTTPException(status_code=404, detail=_("Service not found"))
    try:
        updated_service = crud.update_service(db, db_service, service_update)
        logger.info(f"Service '{updated_service.name}' (ID: {service_id}) updated by owner {current_owner.email} from IP: {request.client.host}")
        return updated_service
    except Exception as e:
        logger.exception(f"Error updating service {service_id} for owner {current_owner.email}: {e}")
        raise HTTPException(status_code=500, detail=_("An unexpected error occurred while updating the service."))

@app.delete("/owner/services/{service_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_owner_service(
    service_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_owner: schemas.Owner = Depends(get_current_owner)
):
    db_service = crud.get_service(db, service_id=service_id)
    if not db_service or db_service.owner_id != current_owner.id:
        logger.warning(f"Unauthorized delete attempt to service_id: {service_id} by owner {current_owner.email} from IP: {request.client.host}")
        raise HTTPException(status_code=404, detail=_("Service not found"))
    try:
        crud.delete_service(db, service_id=service_id)
        logger.info(f"Service (ID: {service_id}) deleted by owner {current_owner.email} from IP: {request.client.host}")
    except Exception as e:
        logger.exception(f"Error deleting service {service_id} for owner {current_owner.email}: {e}")
        raise HTTPException(status_code=500, detail=_("An unexpected error occurred while deleting the service."))

@app.get("/{owner_username}", response_class=HTMLResponse)
async def public_booking_page(
    owner_username: str,
    request: Request,
    db: Session = Depends(get_db)
):
    owner = crud.get_owner_by_username(db, username=owner_username)
    if not owner:
        raise HTTPException(status_code=404, detail=_("Owner not found."))

    services = crud.get_owner_services(db, owner_id=owner.id)

    # Reviews for this owner
    reviews = crud.get_reviews_for_owner(db, owner.id)

    return templates.TemplateResponse(
        "booking_page.html",
        {
            "request": request,
            "owner": owner,
            "services": services,
            "current_locale": get_locale(request),
            "_": _,
            "ngettext": ngettext,
            "reviews": reviews
        }
    )

@app.get("/{owner_username}/service/{service_id}/available-slots")
async def get_available_slots_api(
    owner_username: str,
    service_id: int,
    target_date: date,
    db: Session = Depends(get_db)
):
    owner = crud.get_owner_by_username(db, username=owner_username)
    if not owner:
        raise HTTPException(status_code=404, detail=_("Owner not found."))

    service = crud.get_service(db, service_id=service_id)
    if not service or service.owner_id != owner.id:
        raise HTTPException(status_code=404, detail=_("Service not found for this owner."))

    # Ensure target_date is not in the past
    if target_date < date.today():
        return [] # No slots available in the past

    available_slots = availability_utils.get_available_slots_for_day(
        db, owner.id, service.id, target_date, service.duration_minutes
    )
    return [slot.isoformat() for slot in available_slots]

@app.post("/book/{owner_username}/{service_id}", response_model=schemas.Booking)
async def create_booking(
    owner_username: str,
    service_id: int,
    booking_data: schemas.BookingCreate,
    request: Request,
    db: Session = Depends(get_db)
):
    owner = crud.get_owner_by_username(db, username=owner_username)
    if not owner:
        logger.warning(f"Booking attempt for non-existent owner username: {owner_username} from IP: {request.client.host}")
        raise HTTPException(status_code=404, detail=_("Owner not found."))

    service = crud.get_service(db, service_id=service_id)
    if not service or service.owner_id != owner.id:
        logger.warning(f"Booking attempt for non-existent or unauthorized service_id: {service_id} for owner: {owner_username} from IP: {request.client.host}")
        raise HTTPException(status_code=404, detail=_("Service not found for this owner."))

    if booking_data.date < date.today():
        logger.warning(f"Attempt to book in the past for service_id: {service_id}, owner: {owner_username}, date: {booking_data.date} from IP: {request.client.host}")
        raise HTTPException(status_code=422, detail=_("Cannot book a service in the past."))

    slot_duration = service.duration_minutes
    available_slots = availability_utils.get_available_slots_for_day(
        db, owner.id, service.id, booking_data.date, slot_duration
    )

    # Convert booking_data.time (datetime.time) to ISO format string for comparison if available_slots are strings
    # Assuming available_slots are datetime.time objects for direct comparison
    if booking_data.time not in available_slots:
        logger.warning(f"Attempt to book unavailable slot for service_id: {service_id}, owner: {owner_username}, date: {booking_data.date}, time: {booking_data.time} from IP: {request.client.host}")
        raise HTTPException(status_code=409, detail=_("The selected time slot is not available."))

    try:
        booking = crud.create_booking(db, booking_data, owner.id, service.id)
        
        if booking_data.recurrence_type != RecurrenceType.NONE:
            crud.create_recurring_bookings(db, booking, booking_data.recurrence_type, booking_data.recurrence_value, booking_data.recurrence_end_date, service.duration_minutes)

        # Notifications
        send_booking_confirmation_email(booking, owner, service, get_locale(request))
        send_owner_notification_email(booking, owner, service, get_locale(request))
        logger.info(f"Booking created successfully by customer {booking_data.customer_email} for owner {owner.email}, service {service.name} on {booking_data.date} at {booking_data.time} from IP: {request.client.host}")
        return booking
    except Exception as e:
        logger.exception(f"Error creating booking for owner {owner.email}, service {service.name}: {e}")
        raise HTTPException(status_code=500, detail=_("An unexpected error occurred during booking."))

@app.get("/booking-confirmation/{booking_id}", response_class=HTMLResponse)
async def booking_confirmation_page(
    booking_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    booking = crud.get_booking(db, booking_id)
    if not booking:
        raise HTTPException(status_code=404, detail=_("Booking not found."))

    # Fetch owner and service details for the confirmation page
    owner = crud.get_owner(db, owner_id=booking.owner_id)
    service = crud.get_service(db, service_id=booking.service_id)

    return templates.TemplateResponse(
        "booking_confirmation.html",
        {
            "request": request,
            "booking": booking,
            "owner": owner,
            "service": service,
            "current_locale": get_locale(request),
            "_": _,
            "ngettext": ngettext
        }
    )

@app.get("/owner/analytics", response_model=schemas.AnalyticsData)
async def get_owner_analytics(
    db: Session = Depends(get_db),
    current_owner: schemas.Owner = Depends(get_current_owner)
):
    monthly_bookings = analytics.get_monthly_bookings_data(db, current_owner.id)
    popular_services = analytics.get_popular_services_data(db, current_owner.id)
    
    return schemas.AnalyticsData(
        monthly_bookings=monthly_bookings,
        popular_services=popular_services
    )

@app.post("/create-checkout-session")
async def create_checkout_session(request: Request, db: Session = Depends(get_db), current_owner: schemas.Owner = Depends(get_current_owner)):
    try:
        # For now, a fixed price for premium subscription ($19/month)
        checkout_session = stripe.checkout.Session.create(
            line_items=[
                {
                    'price_data': {
                        'currency': 'usd',
                        'product_data': {
                            'name': 'BookSlot Premium Subscription',
                            'description': 'Unlimited bookings per month'
                        },
                        'unit_amount': 1900, # $19.00
                        'recurring': {'interval': 'month'},
                    },
                    'quantity': 1,
                },
            ],
            mode='subscription',
            success_url=request.url_for('subscription_success').__str__() + "?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=request.url_for('subscription_cancel').__str__(),
            client_reference_id=str(current_owner.id),
            metadata={
                "owner_id": str(current_owner.id)
            }
        )
        return RedirectResponse(checkout_session.url, status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        logger.exception(f"Error creating Stripe checkout session for owner {current_owner.email}: {e}")
        raise HTTPException(status_code=500, detail=_("Could not create checkout session."))

@app.get("/subscription-success", response_class=HTMLResponse)
async def subscription_success(request: Request, session_id: str, db: Session = Depends(get_db)):
    try:
        checkout_session = stripe.checkout.Session.retrieve(session_id)
        owner_id = int(checkout_session.metadata.get("owner_id"))

        # Retrieve or create subscription in your DB
        subscription = crud.get_owner_subscription(db, owner_id)
        if not subscription:
            subscription = models.Subscription(
                owner_id=owner_id,
                stripe_customer_id=checkout_session.customer,
                stripe_subscription_id=checkout_session.subscription,
                status=SubscriptionStatus.ACTIVE
            )
            db.add(subscription)
        else:
            subscription.stripe_customer_id = checkout_session.customer
            subscription.stripe_subscription_id = checkout_session.subscription
            subscription.status = SubscriptionStatus.ACTIVE
        db.commit()
        db.refresh(subscription)
        logger.info(f"Owner {owner_id} successfully subscribed. Stripe Session ID: {session_id}")
        return templates.TemplateResponse("subscription_success.html", {"request": request, "session_id": session_id, "_": _})
    except Exception as e:
        logger.exception(f"Error processing subscription success for session ID {session_id}: {e}")
        raise HTTPException(status_code=500, detail=_("Error processing subscription."))

@app.get("/subscription-cancel", response_class=HTMLResponse)
async def subscription_cancel(request: Request):
    return templates.TemplateResponse("subscription_cancel.html", {"request": request, "_": _})

@app.post("/stripe-webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get('stripe-signature')

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError as e:
        logger.error(f"Invalid payload for Stripe webhook: {e}")
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError as e:
        logger.error(f"Invalid signature for Stripe webhook: {e}")
        raise HTTPException(status_code=400, detail="Invalid signature")

    event_type = event['type']
    data = event['data']
    object = data['object']

    try:
        if event_type == 'checkout.session.completed':
            owner_id = int(object.get('metadata', {}).get('owner_id'))
            customer_id = object.get('customer')
            subscription_id = object.get('subscription')
            
            subscription = crud.get_owner_subscription(db, owner_id)
            if not subscription:
                subscription = models.Subscription(
                    owner_id=owner_id,
                    stripe_customer_id=customer_id,
                    stripe_subscription_id=subscription_id,
                    status=SubscriptionStatus.ACTIVE
                )
                db.add(subscription)
            else:
                subscription.stripe_customer_id = customer_id
                subscription.stripe_subscription_id = subscription_id
                subscription.status = SubscriptionStatus.ACTIVE
            db.commit()
            db.refresh(subscription)
            logger.info(f"Stripe Webhook: Checkout session completed for owner {owner_id}")

        elif event_type == 'customer.subscription.deleted':
            subscription_id = object.get('id')
            db_subscription = crud.get_subscription_by_stripe_id(db, subscription_id)
            if db_subscription:
                db_subscription.status = SubscriptionStatus.CANCELED
                db.commit()
                logger.info(f"Stripe Webhook: Subscription {subscription_id} deleted for owner {db_subscription.owner_id}")

        elif event_type == 'customer.subscription.updated':
            subscription_id = object.get('id')
            status = object.get('status') # active, past_due, canceled, unpaid, incomplete, incomplete_expired
            db_subscription = crud.get_subscription_by_stripe_id(db, subscription_id)
            if db_subscription:
                db_subscription.status = SubscriptionStatus(status)
                db.commit()
                logger.info(f"Stripe Webhook: Subscription {subscription_id} updated to status {status} for owner {db_subscription.owner_id}")

        # Handle other events like 'invoice.payment_succeeded', 'invoice.payment_failed'

    except Exception as e:
        logger.exception(f"Error processing Stripe webhook event {event_type}: {e}")
        raise HTTPException(status_code=500, detail="Webhook handler failed")

    return JSONResponse(status_code=200, content={"success": True})

# Admin Panel Endpoints (Basic CRUD for Owners, Services, Bookings, Subscriptions)
# These should be protected by a dedicated admin role

@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request, db: Session = Depends(get_db)): # Needs admin authentication
    owners = crud.get_all_owners(db)
    return templates.TemplateResponse(
        "admin_dashboard.html",
        {"request": request, "owners": owners, "current_locale": get_locale(request), "_": _}
    )

@app.get("/admin/owners/{owner_id}", response_class=HTMLResponse)
async def admin_owner_detail(owner_id: int, request: Request, db: Session = Depends(get_db)): # Needs admin authentication
    owner = crud.get_owner(db, owner_id)
    if not owner:
        raise HTTPException(status_code=404, detail=_("Owner not found"))
    services = crud.get_owner_services(db, owner_id)
    bookings = crud.get_owner_bookings(db, owner_id)
    subscription = crud.get_owner_subscription(db, owner_id)
    return templates.TemplateResponse(
        "admin_owner_detail.html",
        {
            "request": request,
            "owner": owner,
            "services": services,
            "bookings": bookings,
            "subscription": subscription,
            "current_locale": get_locale(request),
            "_": _
        }
    )

# API endpoints for customer reviews/ratings
@app.post("/reviews", response_model=schemas.Review)
async def create_review(
    review: schemas.ReviewCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_customer: schemas.Customer = Depends(get_current_customer)
):
    try:
        # Check if customer already reviewed this owner or booking (optional logic)
        db_review = crud.create_review(db, review, current_customer.id)
        logger.info(f"Review created by customer {current_customer.email} for owner {review.owner_id} with rating {review.rating} from IP: {request.client.host}")
        return db_review
    except Exception as e:
        logger.exception(f"Error creating review by customer {current_customer.email}: {e}")
        raise HTTPException(status_code=500, detail=_("An unexpected error occurred while submitting the review."))

@app.get("/reviews/owner/{owner_id}", response_model=List[schemas.Review])
async def get_owner_reviews(
    owner_id: int,
    db: Session = Depends(get_db)
):
    return crud.get_reviews_for_owner(db, owner_id)

@app.get("/reviews/customer/{customer_id}", response_model=List[schemas.Review])
async def get_customer_reviews(
    customer_id: int,
    db: Session = Depends(get_db),
    current_customer: schemas.Customer = Depends(get_current_customer)
):
    if customer_id != current_customer.id:
        logger.warning(f"Unauthorized attempt by customer {current_customer.email} to view reviews of customer {customer_id} from IP: {app.request.client.host if app.request else 'N/A'}")
        raise HTTPException(status_code=403, detail=_("Not authorized to view other customer's reviews"))
    return crud.get_reviews_by_customer(db, customer_id)

@app.put("/reviews/{review_id}", response_model=schemas.Review)
async def update_review(
    review_id: int,
    review_update: schemas.ReviewUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_customer: schemas.Customer = Depends(get_current_customer)
):
    db_review = crud.get_review(db, review_id)
    if not db_review or db_review.customer_id != current_customer.id:
        logger.warning(f"Unauthorized update attempt to review_id: {review_id} by customer {current_customer.email} from IP: {request.client.host}")
        raise HTTPException(status_code=404, detail=_("Review not found or not authorized to update"))
    try:
        updated_review = crud.update_review(db, db_review, review_update)
        logger.info(f"Review (ID: {review_id}) updated by customer {current_customer.email} from IP: {request.client.host}")
        return updated_review
    except Exception as e:
        logger.exception(f"Error updating review {review_id} by customer {current_customer.email}: {e}")
        raise HTTPException(status_code=500, detail=_("An unexpected error occurred while updating the review."))

@app.delete("/reviews/{review_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_review(
    review_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_customer: schemas.Customer = Depends(get_current_customer)
):
    db_review = crud.get_review(db, review_id)
    if not db_review or db_review.customer_id != current_customer.id:
        logger.warning(f"Unauthorized delete attempt to review_id: {review_id} by customer {current_customer.email} from IP: {request.client.host}")
        raise HTTPException(status_code=404, detail=_("Review not found or not authorized to delete"))
    try:
        crud.delete_review(db, review_id)
        logger.info(f"Review (ID: {review_id}) deleted by customer {current_customer.email} from IP: {request.client.host}")
    except Exception as e:
        logger.exception(f"Error deleting review {review_id} by customer {current_customer.email}: {e}")
        raise HTTPException(status_code=500, detail=_("An unexpected error occurred while deleting the review."))

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    logger.error(f"HTTPException: {exc.status_code} - {exc.detail} for path: {request.url.path} from IP: {request.client.host}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.critical(f"Unhandled exception: {exc} for path: {request.url.path} from IP: {request.client.host}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": _("An unexpected server error occurred.")},
    )
