from fastapi import FastAPI, Depends, HTTPException, status, Request, Form, Response
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timedelta, date, time
from typing import List, Optional, Dict, Any
from urllib.parse import urlencode

import os
import uuid
import json

from . import models, schemas, security, notifications, analytics, availability_utils, i18n
from .config import settings

import stripe

stripe.api_key = settings.STRIPE_API_KEY
stripe_webhook_secret = settings.STRIPE_WEBHOOK_SECRET

SQLALCHEMY_DATABASE_URL = settings.SQLALCHEMY_DATABASE_URL
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
models.Base.metadata.create_all(bind=engine)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

app = FastAPI()
templates = Jinja2Templates(directory="src/templates")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

async def get_current_owner(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return security.get_current_owner(db, token)

async def get_current_active_owner(current_owner: schemas.Owner = Depends(get_current_owner)):
    if not current_owner.is_active:
        raise HTTPException(status_code=400, detail="Inactive owner")
    return current_owner

async def get_current_owner_optional(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get("access_token")
    if token:
        try:
            return security.get_current_owner(db, token)
        except HTTPException:
            pass
    return None

@app.middleware("http")
async def add_i18n_middleware(request: Request, call_next):
    owner_locale = None
    if "/dashboard" in request.url.path or "/profile" in request.url.path or "/admin" in request.url.path:
        token = request.cookies.get("access_token")
        if token:
            db = SessionLocal()
            try:
                owner = security.get_current_owner(db, token)
                owner_locale = owner.locale
            except HTTPException:
                pass
            finally:
                db.close()
    
    locale = request.query_params.get("lang", owner_locale if owner_locale else "en")
    i18n.set_locale(locale)
    response = await call_next(request)
    return response

templates.env.globals['gettext'] = i18n.gettext
templates.env.globals['ngettext'] = i18n.ngettext
templates.env.globals['pgettext'] = i18n.pgettext
templates.env.globals['npgettext'] = i18n.npgettext
templates.env.globals['format_currency'] = i18n.format_currency
templates.env.globals['format_date'] = i18n.format_date
templates.env.globals['format_time'] = i18n.format_time
templates.env.globals['datetime'] = datetime


@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "message": "Welcome to BookSlot!"})

@app.get("/health")
async def health_check():
    return {"status": "ok"}

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
    response.set_cookie(key="access_token", value=access_token, httponly=True, samesite="Lax", secure=True)
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/signup", response_model=schemas.Owner)
async def signup_owner(owner: schemas.OwnerCreate, db: Session = Depends(get_db)):
    db_owner = db.query(models.Owner).filter(models.Owner.email == owner.email).first()
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

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/logout")
async def logout(response: Response):
    response.delete_cookie(key="access_token")
    return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

@app.get("/dashboard", response_class=HTMLResponse)
async def owner_dashboard(request: Request, current_owner: schemas.Owner = Depends(get_current_active_owner), db: Session = Depends(get_db)):
    bookings = db.query(models.Booking).options(joinedload(models.Booking.service)).filter(
        models.Booking.owner_id == current_owner.id
    ).order_by(models.Booking.date, models.Booking.time).all()

    services = db.query(models.Service).filter(models.Service.owner_id == current_owner.id).all()
    availabilities = db.query(models.Availability).filter(models.Availability.owner_id == current_owner.id).all()

    monthly_bookings = analytics.get_monthly_bookings_data(db, current_owner.id)
    popular_services = analytics.get_popular_services_data(db, current_owner.id)
    
    subscription_status_display = {
        models.SubscriptionStatus.ACTIVE.value: i18n.gettext("Active"),
        models.SubscriptionStatus.INACTIVE.value: i18n.gettext("Inactive"),
        models.SubscriptionStatus.CANCELLED.value: i18n.gettext("Cancelled"),
        models.SubscriptionStatus.TRIAL.value: i18n.gettext("Trial")
    }.get(current_owner.subscription_status, i18n.gettext("Unknown"))

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "owner": current_owner,
        "bookings": bookings,
        "services": services,
        "availabilities": availabilities,
        "monthly_bookings": monthly_bookings,
        "popular_services": popular_services,
        "subscription_status_display": subscription_status_display
    })

@app.get("/profile", response_class=HTMLResponse)
async def owner_profile_page(request: Request, current_owner: schemas.Owner = Depends(get_current_active_owner)):
    return templates.TemplateResponse("profile.html", {"request": request, "owner": current_owner})

@app.post("/profile", response_class=RedirectResponse)
async def update_owner_profile(
    request: Request,
    name: str = Form(...),
    phone: Optional[str] = Form(None),
    locale: str = Form("en"),
    current_owner: schemas.Owner = Depends(get_current_active_owner),
    db: Session = Depends(get_db)
):
    try:
        owner_data = schemas.OwnerUpdate(name=name, phone=phone, locale=locale)
        for key, value in owner_data.dict(exclude_unset=True).items():
            setattr(current_owner, key, value)
        
        db.add(current_owner)
        db.commit()
        db.refresh(current_owner)
        
        i18n.set_locale(current_owner.locale)

        return RedirectResponse(url="/dashboard?message=profile_updated", status_code=status.HTTP_302_FOUND)
    except Exception as e:
        print(f"Error updating profile: {e}")
        return RedirectResponse(url="/profile?error=update_failed", status_code=status.HTTP_302_FOUND)

@app.get("/services/new", response_class=HTMLResponse)
async def new_service_page(request: Request, current_owner: schemas.Owner = Depends(get_current_active_owner)):
    return templates.TemplateResponse("service_form.html", {"request": request, "owner": current_owner, "service": None})

@app.get("/book/{owner_name}/{service_id}", response_class=HTMLResponse)
async def public_booking_page(
    owner_name: str,
    service_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    owner = db.query(models.Owner).filter(models.Owner.name == owner_name).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")

    service = db.query(models.Service).filter(
        models.Service.id == service_id, models.Service.owner_id == owner.id
    ).first()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found for this owner")

    i18n.set_locale(owner.locale)

    today = date.today()
    dates = [(today + timedelta(days=i)) for i in range(30)]

    available_slots = availability_utils.get_available_slots_for_day(
        db, owner.id, service.id, today, service.duration_minutes
    )
    
    available_slots_str = [t.strftime("%H:%M") for t in available_slots]

    return templates.TemplateResponse("booking_page.html", {
        "request": request,
        "owner": owner,
        "service": service,
        "dates": dates,
        "initial_date": today,
        "initial_available_slots": json.dumps(available_slots_str),
        "current_locale": owner.locale,
        "locales": i18n.SUPPORTED_LOCALES
    })

@app.get("/api/available_slots", response_model=List[str])
async def get_available_slots_api(
    owner_id: int,
    service_id: int,
    target_date: date,
    db: Session = Depends(get_db)
):
    owner = db.query(models.Owner).filter(models.Owner.id == owner_id).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")

    service = db.query(models.Service).filter(
        models.Service.id == service_id, models.Service.owner_id == owner_id
    ).first()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found for this owner")

    slots = availability_utils.get_available_slots_for_day(
        db, owner_id, service_id, target_date, service.duration_minutes
    )
    return [s.strftime("%H:%M") for s in slots]

@app.post("/book/{owner_name}/{service_id}", response_class=HTMLResponse)
async def submit_booking(
    owner_name: str,
    service_id: int,
    request: Request,
    customer_name: str = Form(...),
    customer_email: EmailStr = Form(...),
    customer_phone: Optional[str] = Form(None),
    booking_date: date = Form(...),
    booking_time: str = Form(...),
    is_recurring: bool = Form(False),
    recurrence_pattern: Optional[str] = Form(None),
    save_customer_details: bool = Form(False), 
    db: Session = Depends(get_db)
):
    owner = db.query(models.Owner).filter(models.Owner.name == owner_name).first()
    if not owner:
        raise HTTPException(status_code=404, detail=i18n.gettext("Owner not found."))

    service = db.query(models.Service).filter(
        models.Service.id == service_id, models.Service.owner_id == owner.id
    ).first()
    if not service:
        raise HTTPException(status_code=404, detail=i18n.gettext("Service not found for this owner."))

    parsed_booking_time = datetime.strptime(booking_time, "%H:%M").time()

    available_slots = availability_utils.get_available_slots_for_day(
        db, owner.id, service.id, booking_date, service.duration_minutes
    )
    if parsed_booking_time not in available_slots:
        error_message = i18n.gettext("The selected time slot is no longer available. Please choose another.")
        today = date.today()
        dates = [(today + timedelta(days=i)) for i in range(30)]
        initial_available_slots = availability_utils.get_available_slots_for_day(
            db, owner.id, service.id, booking_date, service.duration_minutes
        )
        initial_available_slots_str = [t.strftime("%H:%M") for t in initial_available_slots]

        return templates.TemplateResponse("booking_page.html", {
            "request": request,
            "owner": owner,
            "service": service,
            "dates": dates,
            "initial_date": booking_date,
            "initial_available_slots": json.dumps(initial_available_slots_str),
            "error_message": error_message,
            "customer_name": customer_name,
            "customer_email": customer_email,
            "customer_phone": customer_phone,
            "current_locale": owner.locale,
            "locales": i18n.SUPPORTED_LOCALES
        }, status_code=status.HTTP_400_BAD_REQUEST)

    customer_id_for_booking: Optional[int] = None
    if save_customer_details:
        existing_customer = db.query(models.Customer).filter(
            models.Customer.owner_id == owner.id,
            models.Customer.email == customer_email
        ).first()

        if existing_customer:
            existing_customer.name = customer_name
            existing_customer.phone = customer_phone
            db.add(existing_customer)
            db.commit()
            db.refresh(existing_customer)
            customer_id_for_booking = existing_customer.id
        else:
            new_customer = models.Customer(
                owner_id=owner.id,
                name=customer_name,
                email=customer_email,
                phone=customer_phone
            )
            db.add(new_customer)
            db.commit()
            db.refresh(new_customer)
            customer_id_for_booking = new_customer.id

    if is_recurring and recurrence_pattern:
        try:
            recurrence_details = json.loads(recurrence_pattern)
            
            recurrence_series_id = str(uuid.uuid4())

            booking_data = schemas.BookingCreate(
                service_id=service.id,
                customer_name=customer_name,
                customer_email=customer_email,
                customer_phone=customer_phone,
                date=booking_date,
                time=parsed_booking_time,
                is_recurring=True,
                recurrence_pattern=recurrence_pattern,
                customer_id=customer_id_for_booking
            )
            
            db_booking = models.Booking(
                **booking_data.dict(exclude_unset=True),
                owner_id=owner.id,
                recurrence_id=recurrence_series_id
            )
            db.add(db_booking)
            db.commit()
            db.refresh(db_booking)

            notifications.send_booking_confirmation_email(
                owner_email=owner.email,
                owner_name=owner.name,
                customer_email=customer_email,
                customer_name=customer_name,
                service_name=service.name,
                booking_date=booking_date,
                booking_time=parsed_booking_time,
                is_recurring=True,
                recurrence_pattern=recurrence_pattern,
                owner_locale=owner.locale
            )
            if owner.phone:
                 notifications.send_owner_booking_notification_sms(
                    owner_phone=owner.phone,
                    customer_name=customer_name,
                    service_name=service.name,
                    booking_date=booking_date,
                    booking_time=parsed_booking_time,
                    is_recurring=True,
                    owner_locale=owner.locale
                )
            if customer_phone:
                notifications.send_customer_booking_confirmation_sms(
                    customer_phone=customer_phone,
                    customer_name=customer_name,
                    service_name=service.name,
                    booking_date=booking_date,
                    booking_time=parsed_booking_time,
                    is_recurring=True,
                    owner_locale=owner.locale
                )

            return templates.TemplateResponse("booking_confirmation.html", {
                "request": request,
                "owner": owner,
                "service": service,
                "booking": db_booking,
                "customer_name": customer_name,
                "customer_email": customer_email,
                "customer_phone": customer_phone,
                "is_recurring": True,
                "current_locale": owner.locale,
                "locales": i18n.SUPPORTED_LOCALES
            })

        except json.JSONDecodeError:
            error_message = i18n.gettext("Invalid recurrence pattern provided.")
            today = date.today()
            dates = [(today + timedelta(days=i)) for i in range(30)]
            initial_available_slots = availability_utils.get_available_slots_for_day(
                db, owner.id, service.id, booking_date, service.duration_minutes
            )
            initial_available_slots_str = [t.strftime("%H:%M") for t in initial_available_slots]
            return templates.TemplateResponse("booking_page.html", {
                "request": request,
                "owner": owner,
                "service": service,
                "dates": dates,
                "initial_date": booking_date,
                "initial_available_slots": json.dumps(initial_available_slots_str),
                "error_message": error_message,
                "customer_name": customer_name,
                "customer_email": customer_email,
                "customer_phone": customer_phone,
                "current_locale": owner.locale,
                "locales": i18n.SUPPORTED_LOCALES
            }, status_code=status.HTTP_400_BAD_REQUEST)
    else:
        booking_data = schemas.BookingCreate(
            service_id=service.id,
            customer_name=customer_name,
            customer_email=customer_email,
            customer_phone=customer_phone,
            date=booking_date,
            time=parsed_booking_time,
            customer_id=customer_id_for_booking
        )
        db_booking = models.Booking(**booking_data.dict(exclude_unset=True), owner_id=owner.id)
        db.add(db_booking)
        db.commit()
        db.refresh(db_booking)

        notifications.send_booking_confirmation_email(
            owner_email=owner.email,
            owner_name=owner.name,
            customer_email=customer_email,
            customer_name=customer_name,
            service_name=service.name,
            booking_date=booking_date,
            booking_time=parsed_booking_time,
            owner_locale=owner.locale
        )
        if owner.phone:
             notifications.send_owner_booking_notification_sms(
                owner_phone=owner.phone,
                customer_name=customer_name,
                service_name=service.name,
                booking_date=booking_date,
                booking_time=parsed_booking_time,
                owner_locale=owner.locale
            )
        if customer_phone:
            notifications.send_customer_booking_confirmation_sms(
                customer_phone=customer_phone,
                customer_name=customer_name,
                service_name=service.name,
                booking_date=booking_date,
                booking_time=parsed_booking_time,
                owner_locale=owner.locale
            )

        return templates.TemplateResponse("booking_confirmation.html", {
            "request": request,
            "owner": owner,
            "service": service,
            "booking": db_booking,
            "customer_name": customer_name,
            "customer_email": customer_email,
            "customer_phone": customer_phone,
            "is_recurring": False,
            "current_locale": owner.locale,
            "locales": i18n.SUPPORTED_LOCALES
        })

@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request, current_owner: schemas.Owner = Depends(get_current_active_owner), db: Session = Depends(get_db)):
    if current_owner.email != "admin@bookslot.app":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized as admin")

    owners = db.query(models.Owner).all()
    services = db.query(models.Service).all()
    bookings = db.query(models.Booking).all()

    return templates.TemplateResponse("admin_dashboard.html", {
        "request": request,
        "owner": current_owner,
        "owners": owners,
        "services": services,
        "bookings": bookings,
        "current_locale": current_owner.locale
    })

@app.get("/admin/owners/{owner_id}", response_class=HTMLResponse)
async def admin_edit_owner_page(owner_id: int, request: Request, current_owner: schemas.Owner = Depends(get_current_active_owner), db: Session = Depends(get_db)):
    if current_owner.email != "admin@bookslot.app":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized as admin")
    
    target_owner = db.query(models.Owner).filter(models.Owner.id == owner_id).first()
    if not target_owner:
        raise HTTPException(status_code=404, detail="Owner not found")
    
    return templates.TemplateResponse("admin_owner_edit.html", {
        "request": request,
        "admin_owner": current_owner,
        "target_owner": target_owner,
        "subscription_statuses": [status.value for status in models.SubscriptionStatus],
        "current_locale": current_owner.locale
    })

@app.post("/admin/owners/{owner_id}", response_class=RedirectResponse)
async def admin_update_owner(
    owner_id: int,
    request: Request,
    email: EmailStr = Form(...),
    name: Optional[str] = Form(None),
    phone: Optional[str] = Form(None),
    is_active: bool = Form(False),
    subscription_status: str = Form(...),
    subscription_ends_at: Optional[str] = Form(None),
    locale: str = Form("en"),
    current_owner: schemas.Owner = Depends(get_current_active_owner),
    db: Session = Depends(get_db)
):
    if current_owner.email != "admin@bookslot.app":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized as admin")

    target_owner = db.query(models.Owner).filter(models.Owner.id == owner_id).first()
    if not target_owner:
        raise HTTPException(status_code=404, detail="Owner not found")

    try:
        if subscription_status not in [s.value for s in models.SubscriptionStatus]:
            raise ValueError("Invalid subscription status")

        target_owner.email = email
        target_owner.name = name
        target_owner.phone = phone
        target_owner.is_active = is_active
        target_owner.subscription_status = subscription_status
        target_owner.locale = locale
        
        if subscription_ends_at:
            target_owner.subscription_ends_at = datetime.strptime(subscription_ends_at, '%Y-%m-%dT%H:%M')
        else:
            target_owner.subscription_ends_at = None

        db.add(target_owner)
        db.commit()
        db.refresh(target_owner)
        return RedirectResponse(url="/admin?message=owner_updated", status_code=status.HTTP_302_FOUND)
    except Exception as e:
        print(f"Error updating owner: {e}")
        return RedirectResponse(url=f"/admin/owners/{owner_id}?error=update_failed", status_code=status.HTTP_302_FOUND)

@app.post("/admin/owners/{owner_id}/delete", response_class=RedirectResponse)
async def admin_delete_owner(owner_id: int, request: Request, current_owner: schemas.Owner = Depends(get_current_active_owner), db: Session = Depends(get_db)):
    if current_owner.email != "admin@bookslot.app":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized as admin")

    target_owner = db.query(models.Owner).filter(models.Owner.id == owner_id).first()
    if not target_owner:
        raise HTTPException(status_code=404, detail="Owner not found")
    
    db.query(models.Service).filter(models.Service.owner_id == owner_id).delete()
    db.query(models.Availability).filter(models.Availability.owner_id == owner_id).delete()
    db.query(models.Booking).filter(models.Booking.owner_id == owner_id).delete()
    db.query(models.Customer).filter(models.Customer.owner_id == owner_id).delete()
    
    db.delete(target_owner)
    db.commit()
    return RedirectResponse(url="/admin?message=owner_deleted", status_code=status.HTTP_302_FOUND)


@app.get("/admin/services/{service_id}", response_class=HTMLResponse)
async def admin_edit_service_page(service_id: int, request: Request, current_owner: schemas.Owner = Depends(get_current_active_owner), db: Session = Depends(get_db)):
    if current_owner.email != "admin@bookslot.app":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized as admin")
    
    service = db.query(models.Service).filter(models.Service.id == service_id).first()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    
    owners = db.query(models.Owner).all()
    
    return templates.TemplateResponse("admin_service_edit.html", {
        "request": request,
        "admin_owner": current_owner,
        "service": service,
        "owners": owners,
        "current_locale": current_owner.locale
    })

@app.post("/admin/services/{service_id}", response_class=RedirectResponse)
async def admin_update_service(
    service_id: int,
    request: Request,
    owner_id: int = Form(...),
    name: str = Form(...),
    description: Optional[str] = Form(None),
    duration_minutes: int = Form(...),
    price: Optional[float] = Form(None),
    current_owner: schemas.Owner = Depends(get_current_active_owner),
    db: Session = Depends(get_db)
):
    if current_owner.email != "admin@bookslot.app":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized as admin")

    service = db.query(models.Service).filter(models.Service.id == service_id).first()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")

    try:
        service.owner_id = owner_id
        service.name = name
        service.description = description
        service.duration_minutes = duration_minutes
        service.price = price
        
        db.add(service)
        db.commit()
        db.refresh(service)
        return RedirectResponse(url="/admin?message=service_updated", status_code=status.HTTP_302_FOUND)
    except Exception as e:
        print(f"Error updating service: {e}")
        return RedirectResponse(url=f"/admin/services/{service_id}?error=update_failed", status_code=status.HTTP_302_FOUND)

@app.post("/admin/services/{service_id}/delete", response_class=RedirectResponse)
async def admin_delete_service(service_id: int, request: Request, current_owner: schemas.Owner = Depends(get_current_active_owner), db: Session = Depends(get_db)):
    if current_owner.email != "admin@bookslot.app":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized as admin")

    service = db.query(models.Service).filter(models.Service.id == service_id).first()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    
    db.query(models.Booking).filter(models.Booking.service_id == service_id).delete()
    db.query(models.Availability).filter(models.Availability.service_id == service_id).delete()
    
    db.delete(service)
    db.commit()
    return RedirectResponse(url="/admin?message=service_deleted", status_code=status.HTTP_302_FOUND)

@app.get("/admin/bookings/{booking_id}", response_class=HTMLResponse)
async def admin_edit_booking_page(booking_id: int, request: Request, current_owner: schemas.Owner = Depends(get_current_active_owner), db: Session = Depends(get_db)):
    if current_owner.email != "admin@bookslot.app":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized as admin")
    
    booking = db.query(models.Booking).options(joinedload(models.Booking.owner), joinedload(models.Booking.service), joinedload(models.Booking.customer)).filter(models.Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    
    owners = db.query(models.Owner).all()
    services = db.query(models.Service).all()
    customers = db.query(models.Customer).filter(models.Customer.owner_id == booking.owner_id).all()
    
    return templates.TemplateResponse("admin_booking_edit.html", {
        "request": request,
        "admin_owner": current_owner,
        "booking": booking,
        "owners": owners,
        "services": services,
        "customers": customers,
        "current_locale": current_owner.locale
    })

@app.post("/admin/bookings/{booking_id}", response_class=RedirectResponse)
async def admin_update_booking(
    booking_id: int,
    request: Request,
    owner_id: int = Form(...),
    service_id: int = Form(...),
    customer_id: Optional[int] = Form(None),
    customer_name: str = Form(...),
    customer_email: EmailStr = Form(...),
    customer_phone: Optional[str] = Form(None),
    date: date = Form(...),
    time: str = Form(...),
    is_confirmed: bool = Form(False),
    is_recurring: bool = Form(False),
    recurrence_pattern: Optional[str] = Form(None),
    current_owner: schemas.Owner = Depends(get_current_active_owner),
    db: Session = Depends(get_db)
):
    if current_owner.email != "admin@bookslot.app":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized as admin")

    booking = db.query(models.Booking).filter(models.Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    try:
        booking.owner_id = owner_id
        booking.service_id = service_id
        booking.customer_id = customer_id if customer_id else None
        booking.customer_name = customer_name
        booking.customer_email = customer_email
        booking.customer_phone = customer_phone
        booking.date = date
        booking.time = datetime.strptime(time, "%H:%M").time()
        booking.is_confirmed = is_confirmed
        booking.is_recurring = is_recurring
        booking.recurrence_pattern = recurrence_pattern
        
        db.add(booking)
        db.commit()
        db.refresh(booking)
        return RedirectResponse(url="/admin?message=booking_updated", status_code=status.HTTP_302_FOUND)
    except Exception as e:
        print(f"Error updating booking: {e}")
        return RedirectResponse(url=f"/admin/bookings/{booking_id}?error=update_failed", status_code=status.HTTP_302_FOUND)

@app.post("/admin/bookings/{booking_id}/delete", response_class=RedirectResponse)
async def admin_delete_booking(booking_id: int, request: Request, current_owner: schemas.Owner = Depends(get_current_active_owner), db: Session = Depends(get_db)):
    if current_owner.email != "admin@bookslot.app":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized as admin")

    booking = db.query(models.Booking).filter(models.Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    
    db.delete(booking)
    db.commit()
    return RedirectResponse(url="/admin?message=booking_deleted", status_code=status.HTTP_302_FOUND)


@app.get("/subscribe", response_class=HTMLResponse)
async def subscription_page(request: Request, current_owner: schemas.Owner = Depends(get_current_active_owner)):
    return templates.TemplateResponse("subscription.html", {
        "request": request,
        "owner": current_owner,
        "stripe_publishable_key": os.environ.get("STRIPE_PUBLISHABLE_KEY", "pk_test_..."),
        "current_locale": current_owner.locale
    })

@app.post("/create-checkout-session")
async def create_checkout_session(current_owner: schemas.Owner = Depends(get_current_active_owner), db: Session = Depends(get_db)):
    try:
        if not current_owner.stripe_customer_id:
            customer = stripe.Customer.create(
                email=current_owner.email,
                name=current_owner.name
            )
            current_owner.stripe_customer_id = customer.id
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
            success_url='http://localhost:8000/dashboard?message=subscription_success',
            cancel_url='http://localhost:8000/subscribe?message=subscription_cancelled',
        )
        return {"id": checkout_session.id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/stripe-webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get('stripe-signature')

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, stripe_webhook_secret
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except stripe.error.SignatureVerificationError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        customer_id = session.get('customer')
        subscription_id = session.get('subscription')

        owner = db.query(models.Owner).filter(models.Owner.stripe_customer_id == customer_id).first()
        if owner:
            owner.subscription_status = models.SubscriptionStatus.ACTIVE.value
            if subscription_id:
                subscription = stripe.Subscription.retrieve(subscription_id)
                if subscription.current_period_end:
                    owner.subscription_ends_at = datetime.fromtimestamp(subscription.current_period_end)
            db.add(owner)
            db.commit()
            print(f"Owner {owner.email} subscribed successfully.")
        else:
            print(f"Owner with Stripe customer ID {customer_id} not found.")

    elif event['type'] == 'customer.subscription.deleted':
        subscription = event['data']['object']
        customer_id = subscription.get('customer')
        owner = db.query(models.Owner).filter(models.Owner.stripe_customer_id == customer_id).first()
        if owner:
            owner.subscription_status = models.SubscriptionStatus.CANCELLED.value
            db.add(owner)
            db.commit()
            print(f"Owner {owner.email}'s subscription cancelled.")

    elif event['type'] == 'customer.subscription.updated':
        subscription = event['data']['object']
        customer_id = subscription.get('customer')
        owner = db.query(models.Owner).filter(models.Owner.stripe_customer_id == customer_id).first()
        if owner:
            owner.subscription_status = models.SubscriptionStatus.ACTIVE.value if subscription.status == 'active' else subscription.status
            if subscription.current_period_end:
                owner.subscription_ends_at = datetime.fromtimestamp(subscription.current_period_end)
            db.add(owner)
            db.commit()
            print(f"Owner {owner.email}'s subscription updated to {subscription.status}.")


    return {"status": "success"}

@app.get("/api/analytics/monthly_bookings/{owner_id}", response_model=List[schemas.MonthlyBookingData])
async def get_monthly_bookings_api(owner_id: int, db: Session = Depends(get_db), current_owner: schemas.Owner = Depends(get_current_active_owner)):
    if owner_id != current_owner.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view these analytics.")
    return analytics.get_monthly_bookings_data(db, owner_id)

@app.get("/api/analytics/popular_services/{owner_id}", response_model=List[schemas.PopularServiceData])
async def get_popular_services_api(owner_id: int, db: Session = Depends(get_db), current_owner: schemas.Owner = Depends(get_current_active_owner)):
    if owner_id != current_owner.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view these analytics.")
    return analytics.get_popular_services_data(db, owner_id)

@app.get("/customers", response_class=HTMLResponse)
async def list_customers(request: Request, current_owner: schemas.Owner = Depends(get_current_active_owner), db: Session = Depends(get_db)):
    customers = db.query(models.Customer).filter(models.Customer.owner_id == current_owner.id).all()
    return templates.TemplateResponse("customer_list.html", {
        "request": request,
        "owner": current_owner,
        "customers": customers,
        "current_locale": current_owner.locale
    })

@app.get("/customers/{customer_id}", response_class=HTMLResponse)
async def view_customer(customer_id: int, request: Request, current_owner: schemas.Owner = Depends(get_current_active_owner), db: Session = Depends(get_db)):
    customer = db.query(models.Customer).filter(models.Customer.id == customer_id, models.Customer.owner_id == current_owner.id).first()
    if not customer:
        raise HTTPException(status_code=404, detail=i18n.gettext("Customer not found."))
    
    customer_bookings = db.query(models.Booking).options(joinedload(models.Booking.service)).filter(
        models.Booking.customer_id == customer_id,
        models.Booking.owner_id == current_owner.id
    ).order_by(models.Booking.date.desc(), models.Booking.time.desc()).all()

    return templates.TemplateResponse("customer_detail.html", {
        "request": request,
        "owner": current_owner,
        "customer": customer,
        "bookings": customer_bookings,
        "current_locale": current_owner.locale
    })

@app.post("/customers/{customer_id}/update", response_class=RedirectResponse)
async def update_customer(
    customer_id: int,
    request: Request,
    name: str = Form(...),
    email: EmailStr = Form(...),
    phone: Optional[str] = Form(None),
    current_owner: schemas.Owner = Depends(get_current_active_owner),
    db: Session = Depends(get_db)
):
    customer = db.query(models.Customer).filter(models.Customer.id == customer_id, models.Customer.owner_id == current_owner.id).first()
    if not customer:
        raise HTTPException(status_code=404, detail=i18n.gettext("Customer not found."))
    
    try:
        customer.name = name
        customer.email = email
        customer.phone = phone
        db.add(customer)
        db.commit()
        db.refresh(customer)
        return RedirectResponse(url=f"/customers/{customer_id}?message=customer_updated", status_code=status.HTTP_302_FOUND)
    except Exception as e:
        print(f"Error updating customer {customer_id}: {e}")
        return RedirectResponse(url=f"/customers/{customer_id}?error=update_failed", status_code=status.HTTP_302_FOUND)

@app.post("/customers/{customer_id}/delete", response_class=RedirectResponse)
async def delete_customer(customer_id: int, request: Request, current_owner: schemas.Owner = Depends(get_current_active_owner), db: Session = Depends(get_db)):
    customer = db.query(models.Customer).filter(models.Customer.id == customer_id, models.Customer.owner_id == current_owner.id).first()
    if not customer:
        raise HTTPException(status_code=404, detail=i18n.gettext("Customer not found."))
    
    db.query(models.Booking).filter(models.Booking.customer_id == customer_id).update({"customer_id": None})
    db.delete(customer)
    db.commit()
    return RedirectResponse(url="/customers?message=customer_deleted", status_code=status.HTTP_302_FOUND)
