from fastapi import FastAPI, Depends, HTTPException, status, Request, Form, Response
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import List, Optional
from jose import JWTError, jwt
import os
import stripe

from . import models, schemas, crud, security, notifications
from .database import SessionLocal, engine, get_db
from .config import settings
from gettext import translation, bindtextdomain, textdomain

# Create database tables
models.Base.metadata.create_all(bind=engine)

app = FastAPI()

# Jinja2 Templates setup
templates = Jinja2Templates(directory="src/templates")

# Internationalization setup
bindtextdomain('messages', settings.LOCALES_DIR)
textdomain('messages')

@app.middleware("http")
async def add_i18n_middleware(request: Request, call_next):
    lang = request.cookies.get("lang", settings.DEFAULT_LOCALE)
    request.state.gettext = translation('messages', settings.LOCALES_DIR, languages=[lang]).gettext
    response = await call_next(request)
    return response

@app.template_filter()
def _(text: str, request: Request):
    return request.state.gettext(text)

@app.template_filter()
def format_currency(amount: float, request: Request, currency: str = "USD"):
    lang = request.cookies.get("lang", settings.DEFAULT_LOCALE)
    if lang == "ar":
        return f"{amount:,.2f} {currency}"
    else:
        return f"{currency} {amount:,.2f}"

@app.template_filter()
def format_datetime(dt: datetime, request: Request, format_str: str = "%Y-%m-%d %H:%M"):
    lang = request.cookies.get("lang", settings.DEFAULT_LOCALE)
    return dt.strftime(format_str)


# Dependency to get the current owner
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
    except JWTError:
        raise credentials_exception
    owner = crud.get_owner_by_email(db, email=email)
    if owner is None:
        raise credentials_exception
    return owner

async def get_current_active_owner(current_owner: schemas.Owner = Depends(get_current_owner)):
    if not current_owner:
        raise HTTPException(status_code=400, detail="Inactive owner")
    return current_owner

# Root endpoint (redirect to login/dashboard)
@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request, current_owner: Optional[models.Owner] = Depends(get_current_owner)):
    if current_owner:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse("login.html", {"request": request})

# Language toggle endpoint
@app.post("/set_language")
async def set_language(request: Request, lang: str = Form(...)):
    response = RedirectResponse(url=request.headers.get("referer", "/"), status_code=status.HTTP_302_FOUND)
    response.set_cookie(key="lang", value=lang, httponly=True, samesite="Lax")
    return response

# Signup endpoint
@app.get("/signup", response_class=HTMLResponse)
async def signup_form(request: Request):
    return templates.TemplateResponse("signup.html", {"request": request})

@app.post("/signup", response_class=HTMLResponse)
async def signup(request: Request, email: str = Form(...), password: str = Form(...),
                 name: str = Form(...), phone: str = Form(...), db: Session = Depends(get_db)):
    db_owner = crud.get_owner_by_email(db, email=email)
    if db_owner:
        return templates.TemplateResponse("signup.html", {"request": request, "error": _("Email already registered", request)})
    
    hashed_password = security.get_password_hash(password)
    owner_create = schemas.OwnerCreate(email=email, password=password, name=name, phone=phone)
    owner = crud.create_owner(db=db, owner=owner_create, hashed_password=hashed_password)
    
    access_token = security.create_access_token(data={"sub": owner.email})
    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    response.set_cookie(key="access_token", value=access_token, httponly=True, samesite="Lax")
    return response

# Login endpoint
@app.get("/login", response_class=HTMLResponse)
async def login_form(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login", response_class=HTMLResponse)
async def login(request: Request, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    owner = crud.get_owner_by_email(db, email=email)
    if not owner or not security.verify_password(password, owner.hashed_password):
        return templates.TemplateResponse("login.html", {"request": request, "error": _("Incorrect email or password", request)})
    
    access_token = security.create_access_token(data={"sub": owner.email})
    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    response.set_cookie(key="access_token", value=access_token, httponly=True, samesite="Lax")
    return response

# Logout endpoint
@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    response.delete_cookie("access_token")
    return response

# Owner dashboard
@app.get("/dashboard", response_class=HTMLResponse)
async def owner_dashboard(request: Request, current_owner: models.Owner = Depends(get_current_active_owner), db: Session = Depends(get_db)):
    upcoming_bookings = crud.get_owner_upcoming_bookings(db, owner_id=current_owner.id)
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "owner": current_owner,
        "upcoming_bookings": upcoming_bookings,
        "current_locale": request.cookies.get("lang", settings.DEFAULT_LOCALE)
    })

# Owner profile update
@app.post("/dashboard/profile", response_class=HTMLResponse)
async def update_owner_profile_route(
    request: Request,
    name: str = Form(...),
    phone: str = Form(...),
    current_owner: models.Owner = Depends(get_current_active_owner),
    db: Session = Depends(get_db)
):
    owner_update = schemas.OwnerProfileUpdate(name=name, phone=phone)
    try:
        updated_owner = crud.update_owner_profile(db, current_owner, owner_update)
        upcoming_bookings = crud.get_owner_upcoming_bookings(db, owner_id=current_owner.id)
        return templates.TemplateResponse("dashboard.html", {
            "request": request,
            "owner": updated_owner,
            "upcoming_bookings": upcoming_bookings,
            "current_locale": request.cookies.get("lang", settings.DEFAULT_LOCALE),
            "message": _("Profile updated successfully!", request)
        })
    except Exception as e:
        upcoming_bookings = crud.get_owner_upcoming_bookings(db, owner_id=current_owner.id)
        return templates.TemplateResponse("dashboard.html", {
            "request": request,
            "owner": current_owner,
            "upcoming_bookings": upcoming_bookings,
            "current_locale": request.cookies.get("lang", settings.DEFAULT_LOCALE),
            "error": _(f"Error updating profile: {e}", request)
        })

# Public booking page
@app.get("/bookslot.app/{owner_name}", response_class=HTMLResponse)
async def public_booking_page(request: Request, owner_name: str, db: Session = Depends(get_db)):
    owner = db.query(models.Owner).filter(models.Owner.name == owner_name).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")

    services = crud.get_owner_services(db, owner_id=owner.id)
    
    return templates.TemplateResponse("booking_page.html", {
        "request": request,
        "owner": owner,
        "services": services,
        "current_locale": request.cookies.get("lang", settings.DEFAULT_LOCALE)
    })

@app.post("/bookslot.app/{owner_name}/submit", response_class=HTMLResponse)
async def submit_booking(
    request: Request,
    owner_name: str,
    customer_name: str = Form(...),
    customer_email: EmailStr = Form(...),
    customer_phone: str = Form(...),
    service_id: int = Form(...),
    booking_date: str = Form(...),
    booking_time: str = Form(...),
    db: Session = Depends(get_db)
):
    owner = db.query(models.Owner).filter(models.Owner.name == owner_name).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")

    service = crud.get_service_by_id(db, service_id=service_id)
    if not service or service.owner_id != owner.id:
        services = crud.get_owner_services(db, owner_id=owner.id)
        return templates.TemplateResponse("booking_page.html", {
            "request": request,
            "owner": owner,
            "services": services,
            "error": _("Invalid service selected.", request),
            "current_locale": request.cookies.get("lang", settings.DEFAULT_LOCALE)
        })

    try:
        booking_datetime_str = f"{booking_date} {booking_time}"
        booking_dt = datetime.strptime(booking_datetime_str, "%Y-%m-%d %H:%M")
    except ValueError:
        services = crud.get_owner_services(db, owner_id=owner.id)
        return templates.TemplateResponse("booking_page.html", {
            "request": request,
            "owner": owner,
            "services": services,
            "error": _("Invalid date or time format.", request),
            "current_locale": request.cookies.get("lang", settings.DEFAULT_LOCALE)
        })

    if booking_dt < datetime.now():
        services = crud.get_owner_services(db, owner_id=owner.id)
        return templates.TemplateResponse("booking_page.html", {
            "request": request,
            "owner": owner,
            "services": services,
            "error": _("Booking time cannot be in the past.", request),
            "current_locale": request.cookies.get("lang", settings.DEFAULT_LOCALE)
        })

    booking_create = schemas.BookingCreate(
        customer_name=customer_name,
        customer_email=customer_email,
        customer_phone=customer_phone,
        service_id=service_id,
        booking_time=booking_dt
    )

    try:
        db_booking = crud.create_booking(db=db, booking=booking_create, owner_id=owner.id)
        
        notifications.send_booking_confirmation_email(
            owner_email=owner.email,
            customer_email=db_booking.customer_email,
            booking_details=db_booking,
            service_name=service.name,
            owner_name=owner.name
        )
        notifications.send_whatsapp_notification(
            to_phone_number=owner.phone,
            message=f"New booking for {service.name} at {db_booking.booking_time.strftime('%Y-%m-%d %H:%M')} by {db_booking.customer_name} ({db_booking.customer_phone})."
        )

        return templates.TemplateResponse("booking_confirmation.html", {
            "request": request,
            "booking": db_booking,
            "owner": owner,
            "service": service,
            "current_locale": request.cookies.get("lang", settings.DEFAULT_LOCALE)
        })
    except Exception as e:
        services = crud.get_owner_services(db, owner_id=owner.id)
        return templates.TemplateResponse("booking_page.html", {
            "request": request,
            "owner": owner,
            "services": services,
            "error": _(f"Failed to create booking. Please try again. Error: {e}", request),
            "current_locale": request.cookies.get("lang", settings.DEFAULT_LOCALE)
        })


# Stripe webhook endpoint
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
        customer_email = session.get('customer_details', {}).get('email')
        if customer_email:
            owner = crud.get_owner_by_email(db, email=customer_email)
            if owner:
                print(f"Owner {owner.email} successfully subscribed (Stripe session: {session.id})")
            else:
                print(f"Owner not found for email: {customer_email} from Stripe session: {session.id}")
        else:
            print(f"No customer email in Stripe session: {session.id}")
    elif event['type'] == 'invoice.payment_succeeded':
        pass
    elif event['type'] == 'customer.subscription.deleted':
        pass
    
    return {"status": "success"}

# Stripe checkout endpoint (example, needs to be integrated into UI)
@app.post("/create-checkout-session")
async def create_checkout_session(current_owner: models.Owner = Depends(get_current_active_owner)):
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
            cancel_url=f"{settings.SERVER_NAME}/dashboard?canceled=true",
            customer_email=current_owner.email,
        )
        return {"id": checkout_session.id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# NEW: API endpoint for analytics
@app.get("/api/v1/analytics", response_model=schemas.OwnerAnalytics)
async def get_owner_analytics_api(
    current_owner: models.Owner = Depends(get_current_active_owner),
    db: Session = Depends(get_db)
):
    analytics_data = crud.get_owner_analytics(db, owner_id=current_owner.id)
    return analytics_data
