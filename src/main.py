from fastapi import FastAPI, Depends, HTTPException, status, Request, Form, Response, APIRouter
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from . import crud, models, schemas, security, notifications
from .database import engine, get_db
from .config import settings
from datetime import timedelta
import stripe
import os
import gettext
from gettext import gettext as _
from typing import Optional, List, Annotated

# Initialize FastAPI app
app = FastAPI()

# Mount static files and templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Initialize gettext for i18n
def setup_i18n(locale: str):
    try:
        lang = gettext.translation('messages', localedir=settings.LOCALES_DIR, languages=[locale])
        lang.install()
        return lang.gettext
    except FileNotFoundError:
        # Fallback to default English if locale not found
        return gettext.gettext

@app.middleware("http")
async def add_i18n_middleware(request: Request, call_next):
    # Determine locale from query param, cookie, or default
    locale = request.query_params.get("lang") or request.cookies.get("lang") or settings.DEFAULT_LOCALE
    request.state.gettext = setup_i18n(locale)
    request.state.locale = locale
    response = await call_next(request)
    # Set cookie for language preference
    response.set_cookie(key="lang", value=locale, httponly=False)
    return response

# Ensure database tables are created
models.Base.metadata.create_all(bind=engine)

# Stripe configuration
stripe.api_key = settings.STRIPE_SECRET_KEY

# Admin Router
admin_router = APIRouter(prefix="/admin", tags=["admin"])

@admin_router.get("/", response_class=HTMLResponse)
async def admin_dashboard_page(request: Request, db: Session = Depends(get_db), current_admin: models.Owner = Depends(security.get_current_admin_user)):
    """Render the admin dashboard page."""
    _ = request.state.gettext
    owners = crud.get_owners(db)
    return templates.TemplateResponse(
        "admin_dashboard.html",
        {"request": request, "current_admin": current_admin, "owners": owners, "gettext": _, "locale": request.state.locale}
    )

@admin_router.get("/owners/{owner_id}/edit_form", response_class=HTMLResponse)
async def get_owner_edit_form(request: Request, owner_id: int, db: Session = Depends(get_db), current_admin: models.Owner = Depends(security.get_current_admin_user)):
    """Return a partial HTML form for editing an owner."""
    _ = request.state.gettext
    owner = crud.get_owner(db, owner_id=owner_id)
    if owner is None:
        raise HTTPException(status_code=404, detail="Owner not found")
    return templates.TemplateResponse(
        "admin_owner_edit_form.html",
        {"request": request, "owner": owner, "gettext": _, "locale": request.state.locale}
    )

@admin_router.put("/owners/{owner_id}", response_class=HTMLResponse)
async def update_owner_by_admin(
    request: Request,
    owner_id: int,
    name: Annotated[Optional[str], Form()] = None,
    email: Annotated[Optional[EmailStr], Form()] = None,
    phone: Annotated[Optional[str], Form()] = None,
    subscription_status: Annotated[Optional[str], Form()] = None,
    is_admin: Annotated[bool, Form()] = False,
    new_password: Annotated[Optional[str], Form()] = None,
    db: Session = Depends(get_db),
    current_admin: models.Owner = Depends(security.get_current_admin_user)
):
    """Update owner details by an admin via form submission."""
    _ = request.state.gettext
    owner = crud.get_owner(db, owner_id=owner_id)
    if owner is None:
        raise HTTPException(status_code=404, detail="Owner not found")

    owner_update_data = schemas.OwnerAdminUpdate(
        name=name,
        email=email,
        phone=phone,
        subscription_status=subscription_status,
        is_admin=is_admin,
        hashed_password=security.get_password_hash(new_password) if new_password else None
    )

    try:
        updated_owner = crud.update_owner_by_admin(db, owner, owner_update_data)
        return templates.TemplateResponse(
            "admin_owner_edit_form.html",
            {"request": request, "owner": updated_owner, "gettext": _, "locale": request.state.locale, "message": _("Owner updated successfully!")}
        )
    except Exception as e:
        return templates.TemplateResponse(
            "admin_owner_edit_form.html",
            {"request": request, "owner": owner, "gettext": _, "locale": request.state.locale, "error": _("Failed to update owner: {error}").format(error=str(e))}
        )

@admin_router.delete("/owners/{owner_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_owner_by_admin(owner_id: int, db: Session = Depends(get_db), current_admin: models.Owner = Depends(security.get_current_admin_user)):
    """Delete an owner by an admin."""
    success = crud.delete_owner(db, owner_id=owner_id)
    if not success:
        raise HTTPException(status_code=404, detail="Owner not found or could not be deleted")
    return Response(status_code=status.HTTP_204_NO_CONTENT)

app.include_router(admin_router)

# --- Existing main.py content (adapted) ---

@app.post("/token", response_model=schemas.Token)
async def login_for_access_token(db: Session = Depends(get_db), form_data: OAuth2PasswordRequestForm = Depends()):
    owner = db.query(models.Owner).filter(models.Owner.email == form_data.username).first()
    if not owner or not security.verify_password(form_data.password, owner.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": owner.email}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/signup", response_model=schemas.Owner)
async def create_owner(owner: schemas.OwnerCreate, db: Session = Depends(get_db)):
    db_owner = crud.get_owner_by_email(db, email=owner.email)
    if db_owner:
        raise HTTPException(status_code=400, detail="Email already registered")
    hashed_password = security.get_password_hash(owner.password)
    new_owner = crud.create_owner(db=db, owner=owner, hashed_password=hashed_password)
    return new_owner

@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.get("/", response_class=HTMLResponse)
async def home(request: Request, db: Session = Depends(get_db)):
    _ = request.state.gettext
    return templates.TemplateResponse("home.html", {"request": request, "gettext": _, "locale": request.state.locale})

@app.get("/dashboard", response_class=HTMLResponse)
async def owner_dashboard(request: Request, db: Session = Depends(get_db), current_owner: models.Owner = Depends(security.get_current_active_user)):
    _ = request.state.gettext
    bookings = crud.get_owner_upcoming_bookings(db, owner_id=current_owner.id)
    analytics = crud.get_owner_analytics(db, owner_id=current_owner.id)
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "current_owner": current_owner, "bookings": bookings, "analytics": analytics, "gettext": _, "locale": request.state.locale}
    )

@app.get("/profile", response_class=HTMLResponse)
async def owner_profile_page(request: Request, current_owner: models.Owner = Depends(security.get_current_active_user)):
    _ = request.state.gettext
    return templates.TemplateResponse("profile.html", {"request": request, "current_owner": current_owner, "gettext": _, "locale": request.state.locale})

@app.post("/profile", response_model=schemas.Owner)
async def update_owner_profile(request: Request, owner_update: schemas.OwnerProfileUpdate, db: Session = Depends(get_db), current_owner: models.Owner = Depends(security.get_current_active_user)):
    _ = request.state.gettext
    try:
        updated_owner = crud.update_owner_profile(db, current_owner, owner_update)
        return updated_owner
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/{owner_name}", response_class=HTMLResponse)
async def public_booking_page(request: Request, owner_name: str, db: Session = Depends(get_db)):
    _ = request.state.gettext
    owner = db.query(models.Owner).filter(models.Owner.name == owner_name).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Booking page not found")

    services = crud.get_owner_services(db, owner_id=owner.id)
    availabilities = db.query(models.Availability).filter(models.Availability.owner_id == owner.id).all()

    return templates.TemplateResponse(
        "booking_page.html",
        {"request": request, "owner": owner, "services": services, "availabilities": availabilities, "gettext": _, "locale": request.state.locale, "stripe_public_key": settings.STRIPE_PUBLIC_KEY}
    )

@app.post("/{owner_name}/book", response_model=schemas.Booking)
async def submit_booking(request: Request, owner_name: str, booking: schemas.BookingCreate, db: Session = Depends(get_db)):
    _ = request.state.gettext
    owner = db.query(models.Owner).filter(models.Owner.name == owner_name).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")

    service = crud.get_service_by_id(db, booking.service_id)
    if not service or service.owner_id != owner.id:
        raise HTTPException(status_code=404, detail="Service not found or does not belong to this owner")

    booking_day_of_week = booking.booking_time.weekday()
    booking_time_str = booking.booking_time.strftime("%H:%M")

    is_available = db.query(models.Availability).filter(
        models.Availability.owner_id == owner.id,
        models.Availability.day_of_week == booking_day_of_week,
        models.Availability.start_time <= booking_time_str,
        models.Availability.end_time >= booking_time_str
    ).first()

    if not is_available:
        raise HTTPException(status_code=400, detail=_("The selected time slot is not available."))

    try:
        db_booking = crud.create_booking(db=db, booking=booking, owner_id=owner.id)
        notifications.send_owner_notification(owner, db_booking, service, booking.locale)
        notifications.send_customer_confirmation(booking, owner, service, booking.locale)
        return db_booking
    except Exception as e:
        raise HTTPException(status_code=500, detail=_("Failed to create booking: {error}").format(error=str(e)))

@app.get("/booking-confirmation", response_class=HTMLResponse)
async def booking_confirmation_page(request: Request):
    _ = request.state.gettext
    return templates.TemplateResponse("booking_confirmation.html", {"request": request, "gettext": _, "locale": request.state.locale})

@app.get("/subscription", response_class=HTMLResponse)
async def subscription_page(request: Request, current_owner: models.Owner = Depends(security.get_current_active_user)):
    _ = request.state.gettext
    return templates.TemplateResponse(
        "subscription.html",
        {"request": request, "current_owner": current_owner, "gettext": _, "locale": request.state.locale, "stripe_public_key": settings.STRIPE_PUBLIC_KEY}
    )

@app.post("/create-checkout-session")
async def create_checkout_session(request: Request, current_owner: models.Owner = Depends(security.get_current_active_user)):
    _ = request.state.gettext
    try:
        checkout_session = stripe.checkout.Session.create(
            line_items=[
                {
                    'price': settings.STRIPE_PRICE_ID,
                    'quantity': 1,
                },
            ],
            mode='subscription',
            success_url=f"{settings.SERVER_NAME}/dashboard?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{settings.SERVER_NAME}/subscription",
            customer=current_owner.stripe_customer_id if current_owner.stripe_customer_id else None,
            customer_email=current_owner.email if not current_owner.stripe_customer_id else None,
            metadata={"owner_id": current_owner.id},
        )
        return RedirectResponse(checkout_session.url, status_code=303)
    except Exception as e:
        raise HTTPException(status_code=500, detail=_("Failed to create checkout session: {error}").format(error=str(e)))

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
        owner_id = session.metadata.get('owner_id')
        customer_id = session.get('customer')
        subscription_id = session.get('subscription')

        if owner_id and customer_id and subscription_id:
            owner = crud.get_owner(db, int(owner_id))
            if owner:
                crud.update_owner_subscription_status(db, owner, "premium", customer_id, subscription_id)
                print(f"Owner {owner.id} subscription updated to premium.")
        else:
            print(f"Missing info in checkout.session.completed event: owner_id={owner_id}, customer_id={customer_id}, subscription_id={subscription_id}")

    elif event['type'] == 'invoice.payment_succeeded':
        invoice = event['data']['object']
        customer_id = invoice.get('customer')
        subscription_id = invoice.get('subscription')
        print(f"Invoice payment succeeded for customer {customer_id}, subscription {subscription_id}")

    elif event['type'] == 'customer.subscription.deleted':
        subscription = event['data']['object']
        customer_id = subscription.get('customer')
        owner = db.query(models.Owner).filter(models.Owner.stripe_customer_id == customer_id).first()
        if owner:
            crud.update_owner_subscription_status(db, owner, "cancelled")
            print(f"Owner {owner.id} subscription cancelled.")

    elif event['type'] == 'customer.subscription.updated':
        subscription = event['data']['object']
        customer_id = subscription.get('customer')
        status = subscription.get('status')
        owner = db.query(models.Owner).filter(models.Owner.stripe_customer_id == customer_id).first()
        if owner and owner.subscription_status != status:
            crud.update_owner_subscription_status(db, owner, status)
            print(f"Owner {owner.id} subscription status updated to {status}.")

    return Response(status_code=200)

@app.get("/logout", response_class=RedirectResponse)
async def logout():
    response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    response.delete_cookie(key="access_token")
    return response
