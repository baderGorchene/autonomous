from fastapi import FastAPI, Request, Depends, HTTPException, status, Form, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime, time, timedelta
import pytz
from typing import List, Optional
from gettext import gettext as _
import gettext as gt
import os

from . import models, schemas, crud, security, notifications
from .database import engine, get_db
from .dependencies import get_current_owner
from .config import settings

models.Base.metadata.create_all(bind=engine)

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

def get_locale_from_request(request: Request) -> str:
    lang = request.cookies.get("lang") or request.headers.get("Accept-Language", "").split(',')[0].split('-')[0] or settings.DEFAULT_LOCALE
    if lang not in ["en", "ar", "fr"]:
        lang = settings.DEFAULT_LOCALE
    return lang

@app.middleware("http")
async def add_i18n_middleware(request: Request, call_next):
    lang = get_locale_from_request(request)
    request.state.lang = lang

    try:
        locales_dir = settings.LOCALES_DIR
        translation = gt.translation('messages', locales_dir, languages=[lang])
        request.state.gettext = translation.gettext
    except Exception as e:
        print(f"Error loading translation for {lang}: {e}")
        request.state.gettext = _

    response = await call_next(request)
    return response

@app.on_event("startup")
def setup_jinja_globals():
    templates.env.globals['gettext'] = _
    templates.env.globals['_'] = _
    templates.env.globals['settings'] = settings
    templates.env.filters['format_currency'] = format_currency_filter

def format_currency_filter(value: float, lang: str = "en", currency: str = "USD"):
    if lang == "ar":
        return f"{value:,.2f} {currency}"
    return f"{currency} {value:,.2f}"

def get_owner_by_name_or_404(db: Session, owner_name: str) -> models.Owner:
    owner = db.query(models.Owner).filter(models.Owner.name == owner_name).first()
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Owner not found")
    return owner

@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.post("/token", response_model=schemas.Token)
async def login_for_access_token(response: Response, form_data: security.OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
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

@app.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request):
    return templates.TemplateResponse("signup.html", {"request": request, "_": request.state.gettext})

@app.post("/signup", response_class=HTMLResponse)
async def signup(request: Request, email: str = Form(...), password: str = Form(...), name: str = Form(...), phone: Optional[str] = Form(None), db: Session = Depends(get_db)):
    db_owner = crud.get_owner_by_email(db, email=email)
    if db_owner:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    hashed_password = security.get_password_hash(password)
    owner_create = schemas.OwnerCreate(email=email, password=password, name=name, phone=phone)
    owner_create.password = hashed_password
    owner = crud.create_owner(db=db, owner=owner_create, hashed_password=hashed_password)
    
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": owner.email}, expires_delta=access_token_expires
    )
    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(key="access_token", value=access_token, httponly=True, expires=access_token_expires.total_seconds())
    return response

@app.get("/dashboard", response_class=HTMLResponse)
async def owner_dashboard(request: Request, db: Session = Depends(get_db), current_owner: models.Owner = Depends(get_current_owner)):
    _ = request.state.gettext
    upcoming_bookings = crud.get_owner_upcoming_bookings(db, owner_id=current_owner.id)
    analytics_data = crud.get_owner_analytics(db, owner_id=current_owner.id)

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "owner": current_owner,
        "upcoming_bookings": upcoming_bookings,
        "analytics": analytics_data,
        "_": _,
        "current_locale": request.state.lang
    })

@app.post("/dashboard/profile", response_class=HTMLResponse)
async def update_owner_profile(request: Request, name: str = Form(...), email: str = Form(...), phone: Optional[str] = Form(None), db: Session = Depends(get_db), current_owner: models.Owner = Depends(get_current_owner)):
    _ = request.state.gettext
    try:
        owner_update = schemas.OwnerProfileUpdate(name=name, email=email, phone=phone)
        updated_owner = crud.update_owner_profile(db=db, owner=current_owner, owner_update=owner_update)
        upcoming_bookings = crud.get_owner_upcoming_bookings(db, owner_id=updated_owner.id)
        analytics_data = crud.get_owner_analytics(db, owner_id=updated_owner.id)

        return templates.TemplateResponse("dashboard.html", {
            "request": request,
            "owner": updated_owner,
            "upcoming_bookings": upcoming_bookings,
            "analytics": analytics_data,
            "_": _,
            "current_locale": request.state.lang,
            "message": _("Profile updated successfully!")
        })
    except Exception as e:
        return templates.TemplateResponse("dashboard.html", {
            "request": request,
            "owner": current_owner,
            "upcoming_bookings": crud.get_owner_upcoming_bookings(db, owner_id=current_owner.id),
            "analytics": crud.get_owner_analytics(db, owner_id=current_owner.id),
            "_": _,
            "current_locale": request.state.lang,
            "error_message": _(f"Error updating profile: {e}")
        }, status_code=status.HTTP_400_BAD_REQUEST)

@app.post("/dashboard/services", response_class=HTMLResponse)
async def create_service(request: Request, name: str = Form(...), description: Optional[str] = Form(None), price: float = Form(...), duration_minutes: int = Form(...), db: Session = Depends(get_db), current_owner: models.Owner = Depends(get_current_owner)):
    _ = request.state.gettext
    try:
        service_create = schemas.ServiceCreate(name=name, description=description, price=price, duration_minutes=duration_minutes)
        crud.create_service(db=db, service=service_create, owner_id=current_owner.id)
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        upcoming_bookings = crud.get_owner_upcoming_bookings(db, owner_id=current_owner.id)
        analytics_data = crud.get_owner_analytics(db, owner_id=current_owner.id)
        return templates.TemplateResponse("dashboard.html", {
            "request": request,
            "owner": current_owner,
            "upcoming_bookings": upcoming_bookings,
            "analytics": analytics_data,
            "_": _,
            "current_locale": request.state.lang,
            "error_message": _(f"Error creating service: {e}")
        }, status_code=status.HTTP_400_BAD_REQUEST)

@app.get("/book/{owner_name}", response_class=HTMLResponse)
async def public_booking_page(request: Request, owner_name: str, db: Session = Depends(get_db)):
    _ = request.state.gettext
    owner = get_owner_by_name_or_404(db, owner_name)
    services = crud.get_owner_services(db, owner_id=owner.id)
    
    available_slots = []
    
    return templates.TemplateResponse("booking_page.html", {
        "request": request,
        "owner": owner,
        "services": services,
        "available_slots": available_slots,
        "_": _,
        "current_locale": request.state.lang
    })

@app.post("/book/{owner_name}/confirm", response_class=HTMLResponse)
async def submit_booking(
    request: Request,
    owner_name: str,
    customer_name: str = Form(...),
    customer_email: EmailStr = Form(...),
    customer_phone: Optional[str] = Form(None),
    service_id: int = Form(...),
    booking_date: str = Form(...),
    booking_time: str = Form(...),
    db: Session = Depends(get_db)
):
    _ = request.state.gettext
    owner = get_owner_by_name_or_404(db, owner_name)
    service = crud.get_service_by_id(db, service_id)
    
    if not service or service.owner_id != owner.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Service not found for this owner."))

    try:
        booking_datetime_str = f"{booking_date} {booking_time}"
        booking_datetime = datetime.strptime(booking_datetime_str, "%Y-%m-%d %H:%M")
        
        booking_create = schemas.BookingCreate(
            customer_name=customer_name,
            customer_email=customer_email,
            customer_phone=customer_phone,
            service_id=service_id,
            booking_time=booking_datetime
        )
        
        new_booking = crud.create_booking(db, booking_create, owner_id=owner.id)
        
        notifications.send_booking_confirmation_email(
            owner_email=owner.email,
            customer_email=new_booking.customer_email,
            booking_details=new_booking.model_dump(),
            service_name=service.name,
            owner_name=owner.name,
            lang=request.state.lang
        )
        
        notifications.send_booking_notification_whatsapp(
            owner_phone=owner.phone,
            customer_name=new_booking.customer_name,
            booking_details=new_booking.model_dump(),
            service_name=service.name,
            lang=request.state.lang
        )
        
        return templates.TemplateResponse("booking_confirmation.html", {
            "request": request,
            "booking": new_booking,
            "owner": owner,
            "service": service,
            "_": _,
            "current_locale": request.state.lang
        })
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_("Invalid date or time format."))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=_("An error occurred during booking: {e}").format(e=e))

@app.post("/stripe-webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    _ = request.state.gettext
    payload = await request.body()
    sig_header = request.headers.get('stripe-signature')

    try:
        event = security.stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except security.stripe.error.SignatureVerificationError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        customer_email = session['customer_details']['email']
        
        owner = crud.get_owner_by_email(db, email=customer_email)
        if owner:
            owner.is_premium = True
            db.commit()
            db.refresh(owner)
            notifications.send_premium_welcome_email(owner.email, owner.name, request.state.lang)
            print(f"Owner {owner.email} is now premium.")
        else:
            print(f"Owner not found for email: {customer_email}")
    
    return {"status": "success"}
