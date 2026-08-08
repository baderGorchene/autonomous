from fastapi import FastAPI, Depends, HTTPException, status, Request, Response, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, date
from typing import List, Optional
import pytz
import os
import gettext
from gettext import gettext as _
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.templating import Jinja2Templates
from starlette.staticfiles import StaticFiles
from jose import JWTError, jwt
from passlib.context import CryptContext
from uuid import uuid4
import stripe
from sqlalchemy import func

from . import models, schemas, security, notifications
from .database import SessionLocal, engine
from .config import settings
from .utils import generate_recurring_bookings

models.Base.metadata.create_all(bind=engine)

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

locales_dir = settings.LOCALES_DIR
DEFAULT_LOCALE = settings.DEFAULT_LOCALE
SUPPORTED_LOCALES = ["en", "ar", "fr"]

def get_locale(request: Request) -> str:
    locale = request.cookies.get("locale", DEFAULT_LOCALE)
    if locale not in SUPPORTED_LOCALES:
        locale = DEFAULT_LOCALE
    return locale

class LocaleMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        locale = get_locale(request)
        request.state.locale = locale
        _trans = gettext.translation('messages', locales_dir, languages=[locale], fallback=True)
        request.state.gettext = _trans.gettext
        response = await call_next(request)
        response.set_cookie(key="locale", value=locale, httponly=True, samesite="lax", secure=True)
        return response

app.add_middleware(LocaleMiddleware)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

async def get_current_owner(request: Request, db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    token = request.cookies.get("access_token")
    if not token:
        raise credentials_exception
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
        token_data = schemas.TokenData(email=email)
    except JWTError:
        raise credentials_exception
    owner = db.query(models.Owner).filter(models.Owner.email == token_data.email).first()
    if owner is None:
        raise credentials_exception
    return owner

@app.on_event("startup")
async def startup_event():
    templates.env.globals['gettext'] = _
    templates.env.globals['ngettext'] = gettext.ngettext
    templates.env.globals['settings'] = settings
    templates.env.globals['current_year'] = datetime.now().year
    
    def format_currency(value, locale, currency_code="USD"):
        if locale == "ar":
            return f"{value:,.2f} {currency_code}"
        elif locale == "fr":
            return f"{value:,.2f} {currency_code}"
        return f"{currency_code} {value:,.2f}"
    templates.env.filters['format_currency'] = format_currency

@app.post("/token", response_model=schemas.Token)
async def login_for_access_token(response: Response, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
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
    response.set_cookie(key="access_token", value=access_token, httponly=True, samesite="lax", secure=True)
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/signup", response_class=RedirectResponse, status_code=status.HTTP_302_FOUND)
async def signup(request: Request, email: EmailStr = Form(...), password: str = Form(...), name: str = Form(...), db: Session = Depends(get_db)):
    _ = request.state.gettext
    owner_exists = db.query(models.Owner).filter(models.Owner.email == email).first()
    if owner_exists:
        raise HTTPException(status_code=400, detail=_("Email already registered"))
    
    hashed_password = security.get_password_hash(password)
    owner = models.Owner(email=email, hashed_password=hashed_password, name=name, locale=request.state.locale)
    db.add(owner)
    db.commit()
    db.refresh(owner)

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": owner.email}, expires_delta=access_token_expires
    )
    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    response.set_cookie(key="access_token", value=access_token, httponly=True, samesite="lax", secure=True)
    return response

@app.get("/logout", response_class=RedirectResponse, status_code=status.HTTP_302_FOUND)
async def logout(response: Response):
    response.delete_cookie(key="access_token")
    return RedirectResponse(url="/")

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    _ = request.state.gettext
    return templates.TemplateResponse("index.html", {"request": request, "__": _})

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    _ = request.state.gettext
    return templates.TemplateResponse("login.html", {"request": request, "__": _})

@app.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request):
    _ = request.state.gettext
    return templates.TemplateResponse("signup.html", {"request": request, "__": _})

@app.get("/dashboard", response_class=HTMLResponse)
async def owner_dashboard(request: Request, db: Session = Depends(get_db), current_owner: models.Owner = Depends(get_current_owner)):
    _ = request.state.gettext
    upcoming_bookings = db.query(models.Booking).join(models.Service).filter(
        models.Booking.owner_id == current_owner.id,
        models.Booking.start_time >= datetime.now(),
        models.Booking.status == "confirmed"
    ).order_by(models.Booking.start_time).all()

    monthly_bookings = db.query(
        func.strftime('%Y-%m', models.Booking.start_time).label('month'),
        func.count(models.Booking.id).label('count')
    ).filter(
        models.Booking.owner_id == current_owner.id,
        models.Booking.status == "confirmed"
    ).group_by('month').order_by('month').all()
    monthly_bookings_data = [schemas.BookingCount(month=m.month, count=m.count) for m in monthly_bookings]

    popular_services = db.query(
        models.Service.name,
        func.count(models.Booking.id).label('booking_count')
    ).join(models.Booking).filter(
        models.Booking.owner_id == current_owner.id,
        models.Booking.status == "confirmed"
    ).group_by(models.Service.name).order_by(func.count(models.Booking.id).desc()).limit(5).all()
    popular_services_data = [schemas.PopularService(service_name=s.name, booking_count=s.booking_count) for s in popular_services]


    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "owner": current_owner,
            "upcoming_bookings": upcoming_bookings,
            "monthly_bookings": monthly_bookings_data,
            "popular_services": popular_services_data,
            "": _
        }
    )

@app.post("/dashboard/profile", response_class=RedirectResponse, status_code=status.HTTP_302_FOUND)
async def update_owner_profile(
    request: Request,
    name: str = Form(...),
    phone: Optional[str] = Form(None),
    locale: str = Form("en"),
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(get_current_owner)
):
    _ = request.state.gettext
    current_owner.name = name
    current_owner.phone = phone
    current_owner.locale = locale
    db.commit()
    db.refresh(current_owner)
    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    response.set_cookie(key="locale", value=locale, httponly=True, samesite="lax", secure=True)
    return response

@app.post("/services", response_model=schemas.Service)
async def create_service(
    service: schemas.ServiceCreate,
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(get_current_owner)
):
    db_service = models.Service(**service.model_dump(), owner_id=current_owner.id)
    db.add(db_service)
    db.commit()
    db.refresh(db_service)
    return db_service

@app.get("/book/{owner_name}", response_class=HTMLResponse)
async def get_booking_page(owner_name: str, request: Request, db: Session = Depends(get_db)):
    _ = request.state.gettext
    owner = db.query(models.Owner).filter(models.Owner.name == owner_name).first()
    if not owner:
        raise HTTPException(status_code=404, detail=_("Owner not found"))

    services = db.query(models.Service).filter(models.Service.owner_id == owner.id).all()

    today = datetime.now()
    available_slots = []
    for i in range(7):
        day = today + timedelta(days=i)
        for hour in [9, 10, 11, 14, 15, 16]:
            start = datetime(day.year, day.month, day.day, hour, 0, 0)
            end = start + timedelta(minutes=60)
            is_booked = db.query(models.Booking).filter(
                models.Booking.owner_id == owner.id,
                models.Booking.start_time < end,
                models.Booking.end_time > start,
                models.Booking.status != "cancelled"
            ).first()
            if not is_booked:
                available_slots.append({"start": start.isoformat(), "end": end.isoformat()})

    return templates.TemplateResponse(
        "booking_page.html",
        {
            "request": request,
            "owner": owner,
            "services": services,
            "available_slots": available_slots,
            "STRIPE_PUBLIC_KEY": settings.STRIPE_PUBLIC_KEY,
            "": request.state.gettext
        }
    )

@app.post("/book/{owner_name}", response_class=HTMLResponse)
async def create_booking(
    owner_name: str,
    customer_name: str = Form(...),
    customer_email: EmailStr = Form(...),
    customer_phone: Optional[str] = Form(None),
    service_id: int = Form(...),
    start_time: datetime = Form(..., alias="booking_start_time"),
    end_time: datetime = Form(..., alias="booking_end_time"),
    is_recurring: bool = Form(False),
    recurrence_pattern: Optional[str] = Form(None),
    recurrence_end_date: Optional[date] = Form(None),
    request: Request,
    db: Session = Depends(get_db)
):
    _ = request.state.gettext
    owner = db.query(models.Owner).filter(models.Owner.name == owner_name).first()
    if not owner:
        raise HTTPException(status_code=404, detail=_("Owner not found"))

    service = db.query(models.Service).filter(
        models.Service.id == service_id,
        models.Service.owner_id == owner.id
    ).first()
    if not service:
        raise HTTPException(status_code=404, detail=_("Service not found for this owner"))

    booking_data = schemas.BookingCreate(
        customer_name=customer_name,
        customer_email=customer_email,
        customer_phone=customer_phone,
        start_time=start_time,
        end_time=end_time,
        service_id=service_id,
        is_recurring=is_recurring,
        recurrence_pattern=recurrence_pattern,
        recurrence_end_date=recurrence_end_date
    )

    bookings_to_commit = []
    if booking_data.is_recurring:
        try:
            bookings_to_commit = generate_recurring_bookings(
                booking_data=booking_data,
                owner_id=owner.id,
                db=db,
                service=service
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except HTTPException as e:
            raise e
    else:
        existing_booking = db.query(models.Booking).filter(
            models.Booking.owner_id == owner.id,
            models.Booking.start_time < booking_data.end_time,
            models.Booking.end_time > booking_data.start_time,
            models.Booking.status != "cancelled"
        ).first()

        if existing_booking:
            raise HTTPException(status_code=409, detail=_("The selected time slot is already booked or overlaps with an existing booking."))

        booking = models.Booking(
            customer_name=booking_data.customer_name,
            customer_email=booking_data.customer_email,
            customer_phone=booking_data.customer_phone,
            start_time=booking_data.start_time,
            end_time=booking_data.end_time,
            service_id=booking_data.service_id,
            owner_id=owner.id,
            is_recurring=False,
            recurrence_pattern=None,
            recurrence_end_date=None,
            recurrence_group_id=None
        )
        bookings_to_commit.append(booking)

    try:
        for booking_instance in bookings_to_commit:
            db.add(booking_instance)
        db.commit()
        for booking_instance in bookings_to_commit:
            db.refresh(booking_instance)

        first_booking = bookings_to_commit[0]
        first_booking.service = service 

        notifications.send_email_notification(
            recipient_email=first_booking.customer_email,
            subject=_("Booking Confirmation"),
            body_html=templates.TemplateResponse(
                "email/customer_booking_confirmation.html",
                {"request": request, "booking": first_booking, "owner": owner, "service": service, "": _}
            ).body.decode("utf-8")
        )
        notifications.send_email_notification(
            recipient_email=owner.email,
            subject=_("New Booking Received"),
            body_html=templates.TemplateResponse(
                "email/owner_new_booking_notification.html",
                {"request": request, "booking": first_booking, "owner": owner, "service": service, "": _}
            ).body.decode("utf-8")
        )
        if owner.phone and settings.TWILIO_WHATSAPP_NUMBER:
            notifications.send_whatsapp_notification(
                to_number=owner.phone,
                message=f"New booking received for {service.name} from {first_booking.customer_name} on {first_booking.start_time.strftime('%Y-%m-%d %H:%M')}"
            )

        return templates.TemplateResponse(
            "booking_confirmation.html",
            {
                "request": request,
                "owner_name": owner_name,
                "booking": first_booking,
                "is_recurring": booking_data.is_recurring,
                "recurrence_pattern": booking_data.recurrence_pattern,
                "recurrence_end_date": booking_data.recurrence_end_date,
                "": _
            }
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"{_('Failed to create booking')}: {str(e)}")

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
        customer_id = session.get('customer')
        subscription_id = session.get('subscription')
        owner_email = session.get('metadata', {}).get('owner_email')

        if owner_email and customer_id and subscription_id:
            owner = db.query(models.Owner).filter(models.Owner.email == owner_email).first()
            if owner:
                owner.stripe_customer_id = customer_id
                
                stripe_subscription = stripe.Subscription.retrieve(subscription_id)
                current_period_end = datetime.fromtimestamp(stripe_subscription.current_period_end)

                subscription = models.Subscription(
                    owner_id=owner.id,
                    stripe_customer_id=customer_id,
                    stripe_subscription_id=subscription_id,
                    status=stripe_subscription.status,
                    current_period_end=current_period_end
                )
                db.add(subscription)
                db.commit()
                db.refresh(owner)
                db.refresh(subscription)
                print(f"Owner {owner.email} subscribed successfully.")
            else:
                print(f"Owner with email {owner_email} not found for subscription update.")
    elif event['type'] == 'customer.subscription.updated':
        subscription_obj = event['data']['object']
        stripe_subscription_id = subscription_obj['id']
        status = subscription_obj['status']
        current_period_end = datetime.fromtimestamp(subscription_obj['current_period_end'])

        subscription = db.query(models.Subscription).filter(models.Subscription.stripe_subscription_id == stripe_subscription_id).first()
        if subscription:
            subscription.status = status
            subscription.current_period_end = current_period_end
            db.commit()
            db.refresh(subscription)
            print(f"Subscription {stripe_subscription_id} updated to status: {status}")
        else:
            print(f"Subscription {stripe_subscription_id} not found in DB.")

    return JSONResponse(status_code=200, content={"received": True})

@app.get("/dashboard/subscription", response_class=HTMLResponse)
async def subscription_management_page(request: Request, db: Session = Depends(get_db), current_owner: models.Owner = Depends(get_current_owner)):
    _ = request.state.gettext
    subscription = db.query(models.Subscription).filter(models.Subscription.owner_id == current_owner.id).first()
    
    checkout_session_url = None
    if not subscription or subscription.status != 'active':
        try:
            checkout_session = stripe.checkout.Session.create(
                line_items=[
                    {
                        'price': settings.STRIPE_PRICE_ID,
                        'quantity': 1,
                    },
                ],
                mode='subscription',
                success_url=f"{settings.SERVER_NAME}/dashboard?success=true",
                cancel_url=f"{settings.SERVER_NAME}/dashboard/subscription?cancelled=true",
                customer_email=current_owner.email,
                metadata={'owner_email': current_owner.email}
            )
            checkout_session_url = checkout_session.url
        except Exception as e:
            print(f"Error creating Stripe checkout session: {e}")
            checkout_session_url = None

    return templates.TemplateResponse(
        "subscription.html",
        {
            "request": request,
            "owner": current_owner,
            "subscription": subscription,
            "checkout_session_url": checkout_session_url,
            "STRIPE_PUBLIC_KEY": settings.STRIPE_PUBLIC_KEY,
            "": _
        }
    )

@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    _ = request.state.gettext
    owners = db.query(models.Owner).all()
    return templates.TemplateResponse(
        "admin/dashboard.html",
        {"request": request, "owners": owners, "": _}
    )

@app.get("/admin/owners/{owner_id}", response_class=HTMLResponse)
async def admin_view_owner(owner_id: int, request: Request, db: Session = Depends(get_db)):
    _ = request.state.gettext
    owner = db.query(models.Owner).filter(models.Owner.id == owner_id).first()
    if not owner:
        raise HTTPException(status_code=404, detail=_("Owner not found"))
    services = db.query(models.Service).filter(models.Service.owner_id == owner.id).all()
    bookings = db.query(models.Booking).filter(models.Booking.owner_id == owner.id).all()
    subscription = db.query(models.Subscription).filter(models.Subscription.owner_id == owner.id).first()

    return templates.TemplateResponse(
        "admin/owner_detail.html",
        {
            "request": request,
            "owner": owner,
            "services": services,
            "bookings": bookings,
            "subscription": subscription,
            "": _
        }
    )

@app.post("/admin/owners/{owner_id}/update", response_class=RedirectResponse, status_code=status.HTTP_302_FOUND)
async def admin_update_owner(
    owner_id: int,
    request: Request,
    email: EmailStr = Form(...),
    name: str = Form(...),
    phone: Optional[str] = Form(None),
    is_active: bool = Form(True),
    db: Session = Depends(get_db)
):
    _ = request.state.gettext
    owner = db.query(models.Owner).filter(models.Owner.id == owner_id).first()
    if not owner:
        raise HTTPException(status_code=404, detail=_("Owner not found"))
    
    owner.email = email
    owner.name = name
    owner.phone = phone
    owner.is_active = is_active
    db.commit()
    db.refresh(owner)
    return RedirectResponse(url=f"/admin/owners/{owner_id}", status_code=status.HTTP_302_FOUND)

@app.post("/admin/owners/{owner_id}/delete", response_class=RedirectResponse, status_code=status.HTTP_302_FOUND)
async def admin_delete_owner(owner_id: int, db: Session = Depends(get_db)):
    owner = db.query(models.Owner).filter(models.Owner.id == owner_id).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")
    
    db.delete(owner)
    db.commit()
    return RedirectResponse(url="/admin", status_code=status.HTTP_302_FOUND)

@app.get("/set-locale/{locale_code}", response_class=RedirectResponse)
async def set_locale(locale_code: str, request: Request):
    if locale_code not in SUPPORTED_LOCALES:
        locale_code = DEFAULT_LOCALE
    response = RedirectResponse(url=request.headers.get("referer", "/"), status_code=status.HTTP_302_FOUND)
    response.set_cookie(key="locale", value=locale_code, httponly=True, samesite="lax", secure=True)
    return response

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    _ = request.state.gettext
    if exc.status_code == 404:
        return templates.TemplateResponse("404.html", {"request": request, "message": exc.detail, "": _}, status_code=404)
    if exc.status_code == 409:
        return templates.TemplateResponse("error.html", {"request": request, "message": exc.detail, "": _}, status_code=409)
    return templates.TemplateResponse("error.html", {"request": request, "message": exc.detail, "": _}, status_code=exc.status_code)
