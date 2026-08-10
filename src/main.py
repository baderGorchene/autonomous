from fastapi import FastAPI, Depends, HTTPException, status, BackgroundTasks, Request, Response, Form
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session, joinedload
from datetime import date, time, datetime, timedelta
from typing import List, Optional, Dict, Any
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import JSONResponse
import uuid
import stripe
import gettext
import os

from . import models, schemas, security, notifications, availability_utils, analytics
from .database import SessionLocal, engine
from .config import settings

models.Base.metadata.create_all(bind=engine)

app = FastAPI()

# Add Session Middleware for i18n and customer sessions
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

# Static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Templates
templates = Jinja2Templates(directory="templates")

# Internationalization setup
LOCALE_DIR = "locales"
DOMAIN = "messages"

def get_locale(request: Request):
    lang = request.session.get("language", "en")
    try:
        t = gettext.translation(DOMAIN, localedir=LOCALE_DIR, languages=[lang])
        t.install()
        _ = t.gettext
    except Exception:
        # Fallback to English if translation not found
        _ = gettext.gettext
    return _

@app.middleware("http")
async def add_gettext_to_request(request: Request, call_next):
    request.app.state.gettext = get_locale(request)
    response = await call_next(request)
    return response

@app.get("/set_language/{lang_code}")
async def set_language(lang_code: str, request: Request):
    request.session["language"] = lang_code
    # Redirect back to the page the user came from, or to home
    referer = request.headers.get("referer", "/")
    return RedirectResponse(url=referer, status_code=status.HTTP_302_FOUND)

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

async def get_current_owner(request: Request, db: Session = Depends(get_db)):
    owner_id = request.session.get("owner_id")
    if owner_id:
        owner = db.query(models.Owner).filter(models.Owner.id == owner_id).first()
        if owner:
            return owner
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )

async def get_current_active_owner(current_owner: models.Owner = Depends(get_current_owner)):
    if not current_owner.is_active:
        raise HTTPException(status_code=400, detail="Inactive owner")
    return current_owner

# New dependency for current customer
def get_current_customer(request: Request, db: Session = Depends(get_db)):
    customer_id = request.session.get("customer_id")
    if customer_id:
        customer = db.query(models.Customer).filter(models.Customer.id == customer_id).first()
        if customer:
            return customer
    return None # Customer not logged in or session expired

# --- Owner Authentication and Dashboard ---

@app.post("/token", response_model=schemas.Token)
async def login_for_access_token(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    form_data: OAuth2PasswordRequestForm = Depends()
):
    _ = request.app.state.gettext
    owner = db.query(models.Owner).filter(models.Owner.email == form_data.username).first()
    if not owner or not security.verify_password(form_data.password, owner.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_("Incorrect email or password"),
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_owner_access_token(
        owner_id=owner.id, expires_delta=access_token_expires
    )
    request.session["owner_id"] = owner.id # Set owner_id in session
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    _ = request.app.state.gettext
    context = {"request": request, "gettext": _}
    return templates.TemplateResponse("login.html", context)

@app.post("/logout")
async def logout(request: Request):
    request.session.pop("owner_id", None)
    return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

@app.post("/signup", response_model=schemas.OwnerResponse)
async def signup(
    owner: schemas.OwnerCreate,
    db: Session = Depends(get_db),
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    _ = get_locale(Request({})) # Get gettext for background tasks
    db_owner = db.query(models.Owner).filter(models.Owner.email == owner.email).first()
    if db_owner:
        raise HTTPException(status_code=400, detail=_("Email already registered"))
    
    hashed_password = security.get_password_hash(owner.password)
    db_owner = models.Owner(
        email=owner.email,
        hashed_password=hashed_password,
        name=owner.name,
        phone_number=owner.phone_number
    )
    db.add(db_owner)
    db.commit()
    db.refresh(db_owner)
    
    # Send welcome email (optional)
    # background_tasks.add_task(notifications.send_welcome_email, db_owner.email, db_owner.name, _)
    
    return db_owner

@app.get("/dashboard", response_class=HTMLResponse)
async def owner_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(get_current_active_owner)
):
    _ = request.app.state.gettext
    
    # Fetch upcoming bookings
    today = date.today()
    upcoming_bookings = db.query(models.Booking).options(
        joinedload(models.Booking.service),
        joinedload(models.Booking.customer) # Eager load customer
    ).filter(
        models.Booking.owner_id == current_owner.id,
        models.Booking.date >= today
    ).order_by(models.Booking.date, models.Booking.time).all()

    # Fetch analytics data
    monthly_bookings = analytics.get_monthly_bookings_data(db, current_owner.id)
    popular_services = analytics.get_popular_services_data(db, current_owner.id)

    # Fetch services
    services = db.query(models.Service).filter(models.Service.owner_id == current_owner.id).all()

    context = {
        "request": request,
        "owner": current_owner,
        "upcoming_bookings": upcoming_bookings,
        "monthly_bookings": monthly_bookings,
        "popular_services": popular_services,
        "services": services,
        "language": request.session.get("language", "en"),
        "gettext": _
    }
    return templates.TemplateResponse("dashboard.html", context)

@app.post("/dashboard/profile/update", response_model=schemas.OwnerResponse)
async def update_owner_profile(
    request: Request,
    owner_update: schemas.OwnerUpdate,
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(get_current_active_owner)
):
    _ = request.app.state.gettext
    if owner_update.name is not None:
        current_owner.name = owner_update.name
    if owner_update.phone_number is not None:
        current_owner.phone_number = owner_update.phone_number
    if owner_update.password:
        current_owner.hashed_password = security.get_password_hash(owner_update.password)
    
    db.commit()
    db.refresh(current_owner)
    return current_owner

# --- Public Booking Page ---
@app.get("/book/{owner_name}", response_class=HTMLResponse)
async def booking_page(
    owner_name: str,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    current_customer: Optional[models.Customer] = Depends(get_current_customer) # Get current customer
):
    _ = request.app.state.gettext
    owner = db.query(models.Owner).filter(models.Owner.name == owner_name).first()
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Owner not found."))

    services = db.query(models.Service).filter(models.Service.owner_id == owner.id).all()
    if not services:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("No services found for this owner."))

    selected_service_id = request.query_params.get("service_id")
    selected_date_str = request.query_params.get("date", date.today().isoformat())
    selected_time_str = request.query_params.get("time")

    available_slots: List[time] = []
    available_slots_str: str = "[]"

    if selected_service_id and selected_date_str:
        try:
            service = db.query(models.Service).filter(
                models.Service.id == int(selected_service_id),
                models.Service.owner_id == owner.id
            ).first()
            if service:
                target_date = date.fromisoformat(selected_date_str)
                available_slots = availability_utils.get_available_slots_for_day(
                    db, owner.id, service.id, target_date, service.duration_minutes
                )
                available_slots_str = [t.isoformat() for t in available_slots]
                available_slots_str = JSONResponse(available_slots_str).body.decode("utf-8")
        except ValueError:
            pass # Invalid date or service_id, ignore for now

    lang = request.session.get("language", "en")
    context = {
        "request": request,
        "owner": owner,
        "services": services,
        "selected_service_id": selected_service_id,
        "selected_date": selected_date_str,
        "selected_time": selected_time_str,
        "available_slots_str": available_slots_str,
        "language": lang,
        "current_customer": current_customer, # Pass customer object
        "gettext": _
    }
    return templates.TemplateResponse("booking_page.html", context)

@app.post("/book/{owner_name}/submit", response_class=HTMLResponse)
async def submit_booking(
    owner_name: str,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    service_id: int = Form(...),
    booking_date: date = Form(..., alias="date"),
    booking_time: time = Form(..., alias="time"),
    customer_name: str = Form(..., alias="name"),
    customer_email: EmailStr = Form(..., alias="email"),
    customer_phone: Optional[str] = Form(None, alias="phone"),
    is_recurring: bool = Form(False, alias="is_recurring"),
    recurrence_id: Optional[str] = Form(None, alias="recurrence_id"),
    customer_id: Optional[int] = Form(None, alias="customer_id"), # New: from hidden field if logged in
    create_customer_account: bool = Form(False, alias="create_customer_account"), # New: checkbox
    customer_password: Optional[str] = Form(None, alias="customer_password") # New: password field
):
    _ = request.app.state.gettext
    owner = db.query(models.Owner).filter(models.Owner.name == owner_name).first()
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Owner not found."))

    service = db.query(models.Service).filter(
        models.Service.id == service_id, models.Service.owner_id == owner.id
    ).first()
    if not service:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Service not found."))

    # Validate slot availability
    slot_duration = service.duration_minutes
    available_slots = availability_utils.get_available_slots_for_day(
        db, owner.id, service.id, booking_date, slot_duration
    )
    if booking_time not in available_slots:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_("Selected time slot is not available."))

    # --- Handle Customer Account Logic ---
    customer_obj: Optional[models.Customer] = None
    if customer_id: # Existing customer making a booking (e.g., from session)
        customer_obj = db.query(models.Customer).filter(models.Customer.id == customer_id, models.Customer.owner_id == owner.id).first()
        if not customer_obj:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_("Invalid customer ID provided."))
        # Use existing customer's data, but allow form data to update name/phone if provided
        customer_name = customer_obj.name if not customer_name else customer_name
        customer_email = customer_obj.email
        customer_phone = customer_obj.phone_number if not customer_phone else customer_phone
    elif create_customer_account: # New customer wants to create an account
        if not customer_password:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_("Password is required to create an account."))
        
        existing_customer = db.query(models.Customer).filter(
            models.Customer.email == customer_email, models.Customer.owner_id == owner.id
        ).first()
        if existing_customer:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_("A customer account with this email already exists for this owner."))
        
        hashed_password = security.get_password_hash(customer_password)
        customer_obj = models.Customer(
            email=customer_email,
            name=customer_name,
            phone_number=customer_phone,
            owner_id=owner.id,
            hashed_password=hashed_password
        )
        db.add(customer_obj)
        db.commit()
        db.refresh(customer_obj)
        request.session["customer_id"] = customer_obj.id # Log in the new customer
    else: # Booking as a guest or without explicitly creating an account
        # Check if an existing customer with this email already exists for this owner.
        # If so, link the booking to them for repeat bookings tracking, but don't force login.
        existing_customer = db.query(models.Customer).filter(
            models.Customer.email == customer_email, models.Customer.owner_id == owner.id
        ).first()
        if existing_customer:
            customer_obj = existing_customer
            # Optionally update customer's name/phone if new data is provided
            if customer_name and not customer_obj.name: customer_obj.name = customer_name
            if customer_phone and not customer_obj.phone_number: customer_obj.phone_number = customer_phone
            db.commit()
            db.refresh(customer_obj)
            
    # --- End Customer Account Logic ---

    if is_recurring:
        # Generate a recurrence_id if it's the first booking in a new series
        if not recurrence_id:
            recurrence_id = str(uuid.uuid4())
        
        # Logic to create multiple bookings for recurring series
        # For simplicity, let's assume the current booking is just the first instance
        # The full recurring booking logic would involve creating subsequent bookings
        # based on recurrence rules. For now, we'll just store the recurrence_id.
        new_booking = models.Booking(
            service_id=service.id,
            owner_id=owner.id,
            customer_id=customer_obj.id if customer_obj else None, # Link customer
            date=booking_date,
            time=booking_time,
            customer_name=customer_name,
            customer_email=customer_email,
            customer_phone=customer_phone,
            is_recurring=True,
            recurrence_id=recurrence_id,
            status=models.BookingStatus.PENDING
        )
        db.add(new_booking)
        db.commit()
        db.refresh(new_booking)
        
    else:
        new_booking = models.Booking(
            service_id=service.id,
            owner_id=owner.id,
            customer_id=customer_obj.id if customer_obj else None, # Link customer
            date=booking_date,
            time=booking_time,
            customer_name=customer_name,
            customer_email=customer_email,
            customer_phone=customer_phone,
            status=models.BookingStatus.PENDING
        )
        db.add(new_booking)
        db.commit()
        db.refresh(new_booking)

    # Increment owner's booking count for analytics/monetization
    owner.bookings_count += 1
    db.commit()
    db.refresh(owner)

    # Send notifications in background
    background_tasks.add_task(
        notifications.send_booking_confirmation_emails,
        owner,
        new_booking,
        service,
        _
    )
    background_tasks.add_task(
        notifications.send_booking_notification_to_owner_whatsapp,
        owner,
        new_booking,
        service,
        _
    )

    # Redirect to confirmation page
    confirmation_url = app.url_path_for("booking_confirmation")
    confirmation_url += f"?owner_name={owner_name}&service_name={service.name}&date={booking_date}&time={booking_time}&customer_name={customer_name}&customer_email={customer_email}"
    return RedirectResponse(confirmation_url, status_code=status.HTTP_303_SEE_OTHER)

@app.get("/booking_confirmation", response_class=HTMLResponse)
async def booking_confirmation(request: Request):
    _ = request.app.state.gettext
    context = {"request": request, "gettext": _}
    return templates.TemplateResponse("booking_confirmation.html", context)

# New route for customer login (if they have an account)
@app.post("/customer/login")
async def customer_login(
    request: Request,
    db: Session = Depends(get_db),
    email: EmailStr = Form(...),
    password: str = Form(...),
    owner_name: str = Form(...) # Need owner_name to redirect back to their booking page
):
    _ = request.app.state.gettext
    owner = db.query(models.Owner).filter(models.Owner.name == owner_name).first()
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Owner not found."))

    customer = db.query(models.Customer).filter(
        models.Customer.email == email, models.Customer.owner_id == owner.id
    ).first()

    if not customer or not customer.hashed_password or not security.verify_password(password, customer.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_("Incorrect email or password"),
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Set customer_id in session
    request.session["customer_id"] = customer.id
    # Redirect back to the public booking page of the owner they logged in for
    return RedirectResponse(app.url_path_for("booking_page", owner_name=owner.name), status_code=status.HTTP_303_SEE_OTHER)

@app.post("/customer/logout")
async def customer_logout(request: Request):
    request.session.pop("customer_id", None)
    referer = request.headers.get("referer", "/")
    return RedirectResponse(url=referer, status_code=status.HTTP_303_SEE_OTHER)

# Owner dashboard - List customers (new endpoint/section)
@app.get("/dashboard/customers", response_class=HTMLResponse)
async def owner_customers_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(get_current_active_owner)
):
    _ = request.app.state.gettext
    customers = db.query(models.Customer).filter(models.Customer.owner_id == current_owner.id).all()
    context = {
        "request": request,
        "owner": current_owner,
        "customers": customers,
        "language": request.session.get("language", "en"),
        "gettext": _
    }
    return templates.TemplateResponse("owner_customers_dashboard.html", context)

# Admin panel routes
@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    _ = request.app.state.gettext
    owners = db.query(models.Owner).all()
    context = {"request": request, "owners": owners, "gettext": _}
    return templates.TemplateResponse("admin_dashboard.html", context)

@app.get("/admin/owner/{owner_id}", response_class=HTMLResponse)
async def admin_edit_owner(owner_id: int, request: Request, db: Session = Depends(get_db)):
    _ = request.app.state.gettext
    owner = db.query(models.Owner).filter(models.Owner.id == owner_id).first()
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Owner not found"))
    services = db.query(models.Service).filter(models.Service.owner_id == owner_id).all()
    bookings = db.query(models.Booking).filter(models.Booking.owner_id == owner_id).all()
    customers = db.query(models.Customer).filter(models.Customer.owner_id == owner_id).all() # Fetch customers for this owner
    context = {
        "request": request,
        "owner": owner,
        "services": services,
        "bookings": bookings,
        "customers": customers, # Pass customers to admin template
        "gettext": _
    }
    return templates.TemplateResponse("admin_owner_detail.html", context)

@app.post("/admin/owner/{owner_id}/update", response_model=schemas.OwnerResponse)
async def admin_update_owner(owner_id: int, owner_update: schemas.AdminOwnerUpdate, db: Session = Depends(get_db)):
    _ = get_locale(Request({}))
    owner = db.query(models.Owner).filter(models.Owner.id == owner_id).first()
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Owner not found"))

    update_data = owner_update.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(owner, key, value)
    
    db.commit()
    db.refresh(owner)
    return owner

@app.post("/admin/owner/{owner_id}/delete")
async def admin_delete_owner(owner_id: int, db: Session = Depends(get_db)):
    _ = get_locale(Request({}))
    owner = db.query(models.Owner).filter(models.Owner.id == owner_id).first()
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Owner not found"))
    db.delete(owner)
    db.commit()
    return {"message": _("Owner deleted successfully")}

@app.post("/admin/service/{service_id}/update", response_model=schemas.ServiceResponse)
async def admin_update_service(service_id: int, service_update: schemas.AdminServiceUpdate, db: Session = Depends(get_db)):
    _ = get_locale(Request({}))
    service = db.query(models.Service).filter(models.Service.id == service_id).first()
    if not service:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Service not found"))
    
    update_data = service_update.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(service, key, value)
    
    db.commit()
    db.refresh(service)
    return service

@app.post("/admin/booking/{booking_id}/update", response_model=schemas.BookingResponse)
async def admin_update_booking(booking_id: int, booking_update: schemas.AdminBookingUpdate, db: Session = Depends(get_db)):
    _ = get_locale(Request({}))
    booking = db.query(models.Booking).filter(models.Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Booking not found"))

    if booking_update.status:
        try:
            booking.status = models.BookingStatus[booking_update.status.upper()]
        except KeyError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_("Invalid booking status"))
    
    db.commit()
    db.refresh(booking)
    return booking
