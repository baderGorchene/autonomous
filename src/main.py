from fastapi import FastAPI, Depends, HTTPException, status, Request, Response, Form, BackgroundTasks
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
import stripe
import os
import gettext

from . import crud, models, schemas, security, notifications
from .dependencies import get_current_owner
from .database import engine, get_db
from .config import settings
from .i18n import get_locale, get_babel_gettext

models.Base.metadata.create_all(bind=engine)

app = FastAPI()

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Setup Jinja2Templates
templates = Jinja2Templates(directory="templates")

# Add Session Middleware
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

# Set Stripe API key
stripe.api_key = settings.STRIPE_SECRET_KEY

@app.middleware("http")
async def add_gettext_to_request(request: Request, call_next):
    locale = get_locale(request)
    gt = get_babel_gettext(locale)
    request.state.gettext = gt
    request.state.locale = locale
    response = await call_next(request)
    return response

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    gt = request.state.gettext
    if exc.status_code == status.HTTP_404_NOT_FOUND:
        return templates.TemplateResponse(
            "404.html", {"request": request, "_": gt, "locale": request.state.locale},
            status_code=status.HTTP_404_NOT_FOUND
        )
    elif exc.status_code == status.HTTP_401_UNAUTHORIZED:
        return templates.TemplateResponse(
            "login.html", {"request": request, "_": gt, "error": gt("Please log in to access this page."), "locale": request.state.locale},
            status_code=status.HTTP_401_UNAUTHORIZED
        )
    return templates.TemplateResponse(
        "error.html", {"request": request, "_": gt, "detail": gt("An unexpected error occurred."), "locale": request.state.locale},
        status_code=exc.status_code
    )

@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.post("/token", response_model=schemas.Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    owner = security.authenticate_owner(db, form_data.username, form_data.password)
    if not owner:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = security.create_access_token(data={"sub": owner.email})
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/api/signup", response_model=schemas.Owner)
async def create_owner_signup(
    owner: schemas.OwnerCreate,
    db: Session = Depends(get_db)
):
    db_owner = crud.get_owner_by_email(db, email=owner.email)
    if db_owner:
        raise HTTPException(status_code=400, detail="Email already registered")
    hashed_password = security.get_password_hash(owner.password)
    return crud.create_owner(db=db, owner=owner, hashed_password=hashed_password)

@app.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request):
    return templates.TemplateResponse("signup.html", {"request": request, "_": request.state.gettext, "locale": request.state.locale})

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: Optional[str] = None):
    return templates.TemplateResponse("login.html", {"request": request, "error": error, "_": request.state.gettext, "locale": request.state.locale})

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "_": request.state.gettext, "locale": request.state.locale})

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db), current_owner: models.Owner = Depends(get_current_owner)):
    gt = request.state.gettext
    services = crud.get_owner_services(db, owner_id=current_owner.id)
    upcoming_bookings = crud.get_owner_upcoming_bookings(db, owner_id=current_owner.id)

    # Convert booking_time to a more display-friendly format if needed
    for booking in upcoming_bookings:
        booking.display_time = booking.booking_time.strftime("%Y-%m-%d %H:%M")
        # You might also want to fetch service details for each booking
        booking.service = crud.get_service_by_id(db, booking.service_id)

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "owner": current_owner,
        "services": services,
        "upcoming_bookings": upcoming_bookings,
        "_": gt,
        "locale": request.state.locale
    })

@app.post("/api/owner/profile", response_model=schemas.Owner)
async def update_owner_profile(
    owner_update: schemas.OwnerProfileUpdate,
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(get_current_owner)
):
    try:
        updated_owner = crud.update_owner_profile(db, current_owner, owner_update)
        return updated_owner
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update profile: {e}")

@app.get("/api/owner/analytics", response_model=schemas.BookingAnalytics)
async def get_owner_analytics(db: Session = Depends(get_db), current_owner: models.Owner = Depends(get_current_owner)):
    """
    Retrieve analytics data for the current owner.
    """
    analytics_data = crud.get_owner_booking_counts(db, owner_id=current_owner.id)
    return analytics_data

@app.post("/api/services", response_model=schemas.Service)
async def create_service_for_owner(
    service: schemas.ServiceCreate,
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(get_current_owner)
):
    return models.Service(**service.model_dump(), owner_id=current_owner.id)

@app.get("/bookslot/{owner_name}", response_class=HTMLResponse)
async def booking_page(
    owner_name: str,
    request: Request,
    db: Session = Depends(get_db)
):
    gt = request.state.gettext
    owner = db.query(models.Owner).filter(models.Owner.name == owner_name).first()
    if not owner:
        raise HTTPException(status_code=404, detail=gt("Owner not found"))

    services = crud.get_owner_services(db, owner_id=owner.id)
    # In a real app, you'd also fetch availabilities based on owner_id and current date

    return templates.TemplateResponse("booking_page.html", {
        "request": request,
        "owner": owner,
        "services": services,
        "_": gt,
        "locale": request.state.locale,
        "server_name": settings.SERVER_NAME # Pass server name for form action
    })

@app.post("/api/book/{owner_name}", response_model=schemas.Booking)
async def create_booking_for_owner(
    owner_name: str,
    booking_data: schemas.BookingCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    gt = get_babel_gettext(get_locale_from_request_headers())
    owner = db.query(models.Owner).filter(models.Owner.name == owner_name).first()
    if not owner:
        raise HTTPException(status_code=404, detail=gt("Owner not found"))

    service = crud.get_service_by_id(db, booking_data.service_id)
    if not service or service.owner_id != owner.id:
        raise HTTPException(status_code=404, detail=gt("Service not found for this owner"))

    # Basic availability check (needs more robust implementation)
    # For MVP, just check if booking_time is in the future
    if booking_data.booking_time <= datetime.now():
        raise HTTPException(status_code=400, detail=gt("Booking time must be in the future"))

    try:
        db_booking = crud.create_booking(db=db, booking=booking_data, owner_id=owner.id)
        # Send notifications in the background
        background_tasks.add_task(notifications.send_booking_confirmation_emails, db_booking, owner, service)
        background_tasks.add_task(notifications.send_booking_whatsapp_notifications, db_booking, owner, service)
        return db_booking
    except Exception as e:
        raise HTTPException(status_code=500, detail=gt(f"Failed to create booking: {e}"))

@app.get("/booking-confirmation", response_class=HTMLResponse)
async def booking_confirmation_page(request: Request):
    return templates.TemplateResponse("booking_confirmation.html", {"request": request, "_": request.state.gettext, "locale": request.state.locale})

# Helper to get locale from headers (for background tasks where request object might not be available)
def get_locale_from_request_headers(request: Optional[Request] = None):
    if request:
        return get_locale(request)
    # Fallback if no request, e.g., for background tasks or direct calls
    return settings.DEFAULT_LOCALE

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
        # Fulfill the purchase... (e.g., update owner's subscription status)
        print(f"Checkout session completed: {session['id']}")
        # Example: Find owner by session metadata or customer ID and update their subscription status
        owner_id = session.get('metadata', {}).get('owner_id')
        if owner_id:
            owner = crud.get_owner(db, owner_id=int(owner_id))
            if owner:
                owner.is_premium = True # Assuming a field 'is_premium' exists in Owner model
                db.commit()
                db.refresh(owner)
                print(f"Owner {owner.id} is now premium.")

    elif event['type'] == 'invoice.payment_succeeded':
        invoice = event['data']['object']
        # Handle successful recurring payment
        print(f"Invoice payment succeeded: {invoice['id']}")
    elif event['type'] == 'invoice.payment_failed':
        invoice = event['data']['object']
        # Handle failed recurring payment
        print(f"Invoice payment failed: {invoice['id']}")

    return Response(status_code=200)

@app.post("/create-checkout-session")
async def create_checkout_session(checkout_session_data: schemas.CreateCheckoutSession, current_owner: models.Owner = Depends(get_current_owner)):
    try:
        checkout_session = stripe.checkout.Session.create(
            line_items=[
                {
                    'price': checkout_session_data.price_id,
                    'quantity': 1,
                },
            ],
            mode='subscription',
            success_url=checkout_session_data.success_url,
            cancel_url=checkout_session_data.cancel_url,
            metadata={
                'owner_id': str(current_owner.id) # Attach owner_id to the session metadata
            }
        )
        return {"id": checkout_session.id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
