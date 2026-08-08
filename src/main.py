from fastapi import FastAPI, Depends, HTTPException, status, Request, Response, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session, joinedload
from datetime import datetime, timedelta
from typing import List, Annotated, Optional
import os
import stripe

from . import models, schemas, security, notifications
from .database import engine, SessionLocal
from .config import settings
from .i18n import gettext_lazy as _, get_locale, gettext_filter, init_i18n, _set_translation_for_locale

# Create tables if they don't exist
models.Base.metadata.create_all(bind=engine)

app = FastAPI()

# Initialize i18n
init_i18n(settings.LOCALES_DIR, settings.DEFAULT_LOCALE)

# Jinja2 setup
from fastapi.templating import Jinja2Templates
templates = Jinja2Templates(directory="src/templates")
templates.env.globals['gettext'] = gettext_filter
templates.env.globals['get_locale'] = get_locale
templates.env.globals['settings'] = settings # For accessing server_name etc.

# Middleware to set locale based on query param
@app.middleware("http")
async def set_locale_middleware(request: Request, call_next):
    lang = request.query_params.get("lang")
    if lang and lang in ["en", "ar", "fr"]: # Assuming supported locales
        _set_translation_for_locale(lang, settings.LOCALES_DIR)
    else:
        _set_translation_for_locale(settings.DEFAULT_LOCALE, settings.LOCALES_DIR)
    
    response = await call_next(request)
    return response

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Dependency for current owner
def get_current_owner(db: Session = Depends(get_db), token: str = Depends(security.oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        email = security.verify_access_token(token, credentials_exception)
        owner = db.query(models.Owner).filter(models.Owner.email == email).first()
        if owner is None:
            raise credentials_exception
        return owner
    except Exception as e:
        raise credentials_exception

# --- Health Check ---
@app.get("/health")
def health_check():
    return {"status": "ok"}

# --- Authentication Endpoints ---
@app.post("/token", response_model=schemas.Token)
async def login_for_access_token(response: Response, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    owner = security.authenticate_owner(db, form_data.username, form_data.password)
    if not owner:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": owner.email}, expires_delta=access_token_expires
    )
    response.set_cookie(key="access_token", value=access_token, httponly=True, samesite="Lax")
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, msg: Optional[str] = None):
    return templates.TemplateResponse("login.html", {"request": request, "msg": msg})

@app.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request, msg: Optional[str] = None):
    return templates.TemplateResponse("signup.html", {"request": request, "msg": msg})

@app.post("/signup", response_class=HTMLResponse)
async def register_owner(request: Request, db: Session = Depends(get_db), email: str = Form(...), name: str = Form(...), password: str = Form(...), confirm_password: str = Form(...)):
    if password != confirm_password:
        return templates.TemplateResponse("signup.html", {"request": request, "msg": _("Passwords do not match")})
    
    owner = db.query(models.Owner).filter(models.Owner.email == email).first()
    if owner:
        return templates.TemplateResponse("signup.html", {"request": request, "msg": _("Email already registered")})
    
    hashed_password = security.get_password_hash(password)
    new_owner = models.Owner(email=email, name=name, hashed_password=hashed_password)
    db.add(new_owner)
    db.commit()
    db.refresh(new_owner)
    return RedirectResponse(url="/login?msg=" + _("Registration successful! Please log in."), status_code=status.HTTP_303_SEE_OTHER)

@app.post("/logout")
async def logout(response: Response):
    response.delete_cookie(key="access_token", httponly=True, samesite="Lax")
    return RedirectResponse(url="/login?msg=" + _("You have been logged out."), status_code=status.HTTP_303_SEE_OTHER)

# --- Owner Dashboard & Profile ---
@app.get("/dashboard", response_class=HTMLResponse)
async def owner_dashboard(request: Request, db: Session = Depends(get_db), current_owner: models.Owner = Depends(get_current_owner)):
    services = db.query(models.Service).filter(models.Service.owner_id == current_owner.id).all()
    
    # Fetch upcoming bookings
    now = datetime.utcnow()
    upcoming_bookings = db.query(models.Booking).options(joinedload(models.Booking.service))\
                        .filter(models.Booking.owner_id == current_owner.id)\
                        .filter(models.Booking.end_time > now)\
                        .order_by(models.Booking.start_time).all()
    
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "owner": current_owner,
        "services": services,
        "upcoming_bookings": upcoming_bookings,
        "server_name": settings.SERVER_NAME # Pass server_name for public link
    })

@app.post("/dashboard/profile", response_class=HTMLResponse)
async def update_owner_profile(
    request: Request,
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(get_current_owner),
    name: str = Form(...),
    email: EmailStr = Form(...),
    phone: Optional[str] = Form(None)
):
    try:
        # Check if email is already taken by another owner
        if email != current_owner.email:
            existing_owner = db.query(models.Owner).filter(models.Owner.email == email).first()
            if existing_owner:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_("Email already registered by another user"))

        current_owner.name = name
        current_owner.email = email
        current_owner.phone = phone
        db.commit()
        db.refresh(current_owner)
        return RedirectResponse(url="/dashboard?msg=" + _("Profile updated successfully!"), status_code=status.HTTP_303_SEE_OTHER)
    except HTTPException as e:
        # Re-render dashboard with error message
        services = db.query(models.Service).filter(models.Service.owner_id == current_owner.id).all()
        now = datetime.utcnow()
        upcoming_bookings = db.query(models.Booking).options(joinedload(models.Booking.service))\
                            .filter(models.Booking.owner_id == current_owner.id)\
                            .filter(models.Booking.end_time > now)\
                            .order_by(models.Booking.start_time).all()
        return templates.TemplateResponse("dashboard.html", {
            "request": request,
            "owner": current_owner,
            "services": services,
            "upcoming_bookings": upcoming_bookings,
            "server_name": settings.SERVER_NAME,
            "error_msg": e.detail
        }, status_code=e.status_code)
    except Exception as e:
        # Generic error handling
        print(f"Error updating profile: {e}")
        return RedirectResponse(url="/dashboard?error_msg=" + _("An unexpected error occurred."), status_code=status.HTTP_303_SEE_OTHER)


# --- Service Management ---
@app.post("/services", response_model=schemas.Service)
async def create_service(service: schemas.ServiceCreate, db: Session = Depends(get_db), current_owner: models.Owner = Depends(get_current_owner)):
    db_service = models.Service(**service.dict(), owner_id=current_owner.id)
    db.add(db_service)
    db.commit()
    db.refresh(db_service)
    return db_service

@app.put("/services/{service_id}", response_model=schemas.Service)
async def update_service(service_id: int, service: schemas.ServiceUpdate, db: Session = Depends(get_db), current_owner: models.Owner = Depends(get_current_owner)):
    db_service = db.query(models.Service).filter(models.Service.id == service_id, models.Service.owner_id == current_owner.id).first()
    if db_service is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Service not found"))
    
    for key, value in service.dict(exclude_unset=True).items():
        setattr(db_service, key, value)
    db.commit()
    db.refresh(db_service)
    return db_service

@app.delete("/services/{service_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_service(service_id: int, db: Session = Depends(get_db), current_owner: models.Owner = Depends(get_current_owner)):
    db_service = db.query(models.Service).filter(models.Service.id == service_id, models.Service.owner_id == current_owner.id).first()
    if db_service is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Service not found"))
    db.delete(db_service)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

# --- Public Booking Page ---
@app.get("/bookslot.app/{owner_name}", response_class=HTMLResponse)
async def public_booking_page(request: Request, owner_name: str, db: Session = Depends(get_db)):
    owner = db.query(models.Owner).filter(models.Owner.name == owner_name).first()
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Owner not found"))

    services = db.query(models.Service).filter(models.Service.owner_id == owner.id).all()
    
    # Logic for available slots (simplified for reconstruction)
    # This would involve more complex time slot generation
    available_slots = [] 
    # Example: generate some dummy slots for demonstration
    now = datetime.utcnow()
    for i in range(1, 8): # Next 7 days
        day = now + timedelta(days=i)
        for hour in [9, 10, 11, 14, 15, 16]:
            slot_start = day.replace(hour=hour, minute=0, second=0, microsecond=0)
            slot_end = slot_start + timedelta(minutes=60) # Assume 1-hour slots
            if slot_start > now:
                available_slots.append({"start": slot_start, "end": slot_end})

    return templates.TemplateResponse("booking_page.html", {
        "request": request,
        "owner": owner,
        "services": services,
        "available_slots": available_slots, # In a real app, this would be computed based on service duration and owner availability
        "server_name": settings.SERVER_NAME
    })

@app.post("/bookslot.app/{owner_name}/book", response_class=HTMLResponse)
async def submit_booking(
    request: Request,
    owner_name: str,
    db: Session = Depends(get_db),
    service_id: int = Form(...),
    customer_name: str = Form(...),
    customer_email: EmailStr = Form(...),
    customer_phone: Optional[str] = Form(None),
    start_time_str: str = Form(...) # Assuming ISO format from form
):
    owner = db.query(models.Owner).filter(models.Owner.name == owner_name).first()
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Owner not found"))

    service = db.query(models.Service).filter(models.Service.id == service_id, models.Service.owner_id == owner.id).first()
    if not service:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Service not found for this owner"))

    try:
        start_time = datetime.fromisoformat(start_time_str)
        end_time = start_time + timedelta(minutes=service.duration_minutes)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_("Invalid date/time format"))

    # Basic availability check (more robust logic needed in production)
    # Check for overlapping bookings for this owner and service
    overlapping_booking = db.query(models.Booking).filter(
        models.Booking.owner_id == owner.id,
        models.Booking.service_id == service_id, # Or check for any service if owner can only do one at a time
        models.Booking.start_time < end_time,
        models.Booking.end_time > start_time
    ).first()

    if overlapping_booking:
        return templates.TemplateResponse("booking_page.html", {
            "request": request,
            "owner": owner,
            "services": db.query(models.Service).filter(models.Service.owner_id == owner.id).all(),
            "error_msg": _("Selected time slot is no longer available. Please choose another."),
            "customer_name": customer_name,
            "customer_email": customer_email,
            "customer_phone": customer_phone,
            "selected_service_id": service_id,
            "server_name": settings.SERVER_NAME
        }, status_code=status.HTTP_409_CONFLICT)

    new_booking = models.Booking(
        service_id=service.id,
        owner_id=owner.id,
        customer_name=customer_name,
        customer_email=customer_email,
        customer_phone=customer_phone,
        start_time=start_time,
        end_time=end_time,
        status="confirmed" # Or "pending" if owner approval is needed
    )
    db.add(new_booking)
    db.commit()
    db.refresh(new_booking)

    # Send notifications
    booking_details = {
        "service_name": service.name,
        "customer_name": new_booking.customer_name,
        "customer_email": new_booking.customer_email,
        "customer_phone": new_booking.customer_phone,
        "start_time": new_booking.start_time.strftime("%Y-%m-%d %H:%M"),
        "end_time": new_booking.end_time.strftime("%Y-%m-%d %H:%M"),
        "owner_name": owner.name,
        "owner_email": owner.email,
        "owner_phone": owner.phone,
        "price": service.price
    }
    notifications.send_booking_confirmation_email(owner.email, new_booking.customer_email, booking_details)
    notifications.send_whatsapp_notification(owner.phone, booking_details) # Notify owner

    return templates.TemplateResponse("booking_confirmation.html", {
        "request": request,
        "booking": new_booking,
        "service": service,
        "owner": owner,
        "server_name": settings.SERVER_NAME
    })

# --- Stripe Webhook ---
@app.post("/stripe-webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

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
        customer_email = session.customer_details.email
        # Retrieve the owner by email and update their `is_premium` status
        owner = db.query(models.Owner).filter(models.Owner.email == customer_email).first()
        if owner:
            owner.is_premium = True
            db.commit()
            notifications.send_premium_confirmation_email(owner.email, owner.name)
            print(f"Owner {owner.email} is now premium.")
        else:
            print(f"Owner with email {customer_email} not found for premium update.")
    elif event['type'] == 'invoice.payment_succeeded':
        # Handle recurring payment success
        pass
    elif event['type'] == 'customer.subscription.deleted':
        session = event['data']['object']
        customer_email = session.customer.email
        owner = db.query(models.Owner).filter(models.Owner.email == customer_email).first()
        if owner:
            owner.is_premium = False
            db.commit()
            print(f"Owner {owner.email} subscription cancelled, no longer premium.")
    # ... handle other event types
    
    return {"status": "success"}

# --- Analytics Endpoint (NEW) ---
@app.get("/api/analytics", response_model=schemas.AnalyticsResponse)
async def get_owner_analytics(db: Session = Depends(get_db), current_owner: models.Owner = Depends(get_current_owner)):
    now = datetime.utcnow()
    
    total_bookings = db.query(models.Booking).filter(models.Booking.owner_id == current_owner.id).count()
    upcoming_bookings = db.query(models.Booking).filter(
        models.Booking.owner_id == current_owner.id,
        models.Booking.end_time > now,
        models.Booking.status == "confirmed" # Assuming only confirmed bookings count as upcoming
    ).count()
    completed_bookings = db.query(models.Booking).filter(
        models.Booking.owner_id == current_owner.id,
        models.Booking.end_time <= now,
        models.Booking.status == "confirmed" # Assuming only confirmed bookings count as completed
    ).count()
    
    return schemas.AnalyticsResponse(
        total_bookings=total_bookings,
        upcoming_bookings=upcoming_bookings,
        completed_bookings=completed_bookings
    )
