from fastapi import FastAPI, Depends, HTTPException, status, Request, Form, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from datetime import timedelta, date, datetime
import json
import os
import gettext
from starlette.middleware.sessions import SessionMiddleware

from . import models, schemas, crud, security, notifications
from .database import SessionLocal, engine
from .config import settings
from .i18n_config import get_jinja_env

models.Base.metadata.create_all(bind=engine)

app = FastAPI()

# Add SessionMiddleware for language selection and flash messages
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

# Mount static files
PROJECT_ROOT = settings.PROJECT_ROOT
app.mount("/static", StaticFiles(directory=os.path.join(PROJECT_ROOT, "static")), name="static")

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Helper to get jinja environment with current locale
def get_jinja_env_with_locale(request: Request):
    locale = request.session.get("locale", "en")
    return get_jinja_env(locale)

@app.middleware("http")
async def add_gettext_to_request(request: Request, call_next):
    locale = request.session.get("locale", "en")
    try:
        # Ensure that LOCALES_DIR is correctly configured and exists
        if not os.path.exists(settings.LOCALES_DIR):
            print(f"Warning: Locales directory not found at {settings.LOCALES_DIR}")
            _ = gettext.NullTranslations().gettext
        else:
            lang_translations = gettext.translation('messages', settings.LOCALES_DIR, languages=[locale], fallback=True)
            _ = lang_translations.gettext
    except Exception as e:
        print(f"Error loading translations for locale '{locale}': {e}")
        _ = gettext.NullTranslations().gettext # Fallback
    request.state.gettext = _
    response = await call_next(request)
    return response

@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request, db: Session = Depends(get_db)):
    jinja_env = get_jinja_env_with_locale(request)
    _ = request.state.gettext
    return jinja_env.get_template("index.html").render({"request": request, "_": _})

@app.get("/lang/{locale}", response_class=RedirectResponse)
async def set_language(request: Request, locale: str):
    request.session["locale"] = locale
    # Redirect to the page the user was on, or to the root
    redirect_url = request.headers.get("referer", "/")
    return RedirectResponse(url=redirect_url)

@app.post("/token", response_model=schemas.Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    owner = crud.authenticate_owner(db, form_data.username, form_data.password)
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
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/signup", response_class=HTMLResponse)
async def get_signup_page(request: Request):
    jinja_env = get_jinja_env_with_locale(request)
    _ = request.state.gettext
    return jinja_env.get_template("signup.html").render({"request": request, "_": _})

@app.post("/signup", response_class=RedirectResponse)
async def owner_signup(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    business_name: str = Form(...),
    slug: str = Form(...),
    phone: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    _ = request.state.gettext
    db_owner = crud.get_owner_by_email(db, email=email)
    if db_owner:
        request.session["flash_message"] = _("Email already registered")
        return RedirectResponse(url="/signup", status_code=status.HTTP_303_SEE_OTHER)
    
    db_owner_slug = crud.get_owner_by_slug(db, slug=slug)
    if db_owner_slug:
        request.session["flash_message"] = _("Booking page URL already taken")
        return RedirectResponse(url="/signup", status_code=status.HTTP_303_SEE_OTHER)

    owner = schemas.OwnerCreate(name=name, email=email, password=password, business_name=business_name, slug=slug, phone=phone)
    crud.create_owner(db=db, owner=owner)
    request.session["flash_message"] = _("Account created successfully! Please log in.")
    return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/login", response_class=HTMLResponse)
async def get_login_page(request: Request):
    jinja_env = get_jinja_env_with_locale(request)
    _ = request.state.gettext
    return jinja_env.get_template("login.html").render({"request": request, "_": _})

@app.post("/login", response_class=RedirectResponse)
async def owner_login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    _ = request.state.gettext
    owner = crud.authenticate_owner(db, email, password)
    if not owner:
        request.session["flash_message"] = _("Incorrect email or password")
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": owner.email}, expires_delta=access_token_expires
    )
    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(key="access_token", value=access_token, httponly=True, expires=access_token_expires.total_seconds())
    request.session["flash_message"] = _("Logged in successfully!")
    return response

@app.get("/logout", response_class=RedirectResponse)
async def logout(request: Request):
    response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(key="access_token")
    request.session["flash_message"] = request.state.gettext("Logged out successfully.")
    return response

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db), current_owner: schemas.Owner = Depends(security.get_current_owner)):
    jinja_env = get_jinja_env_with_locale(request)
    _ = request.state.gettext
    
    # Get upcoming bookings for the current owner
    upcoming_bookings = db.query(models.Booking).filter(
        models.Booking.owner_id == current_owner.id,
        models.Booking.booking_date >= date.today()
    ).order_by(models.Booking.booking_date, models.Booking.booking_time).all()
    
    return jinja_env.get_template("dashboard.html").render({
        "request": request,
        "current_owner": current_owner,
        "upcoming_bookings": upcoming_bookings,
        "flash_message": request.session.pop("flash_message", None),
        "_": _
    })

@app.get("/profile", response_class=HTMLResponse)
async def get_profile_page(request: Request, current_owner: schemas.Owner = Depends(security.get_current_owner)):
    jinja_env = get_jinja_env_with_locale(request)
    _ = request.state.gettext
    
    services = json.loads(current_owner.services_json) if current_owner.services_json else []
    availability = json.loads(current_owner.availability_json) if current_owner.availability_json else {}

    return jinja_env.get_template("profile.html").render({
        "request": request,
        "current_owner": current_owner,
        "services": services,
        "availability": availability,
        "flash_message": request.session.pop("flash_message", None),
        "_": _
    })

@app.post("/profile", response_class=RedirectResponse)
async def update_profile(
    request: Request,
    name: str = Form(...),
    business_name: str = Form(...),
    phone: Optional[str] = Form(None),
    services_json: str = Form("[]"),
    availability_json: str = Form("{}"),
    db: Session = Depends(get_db),
    current_owner: schemas.Owner = Depends(security.get_current_owner)
):
    _ = request.state.gettext
    try:
        # Validate services_json and availability_json
        parsed_services = json.loads(services_json)
        schemas.OwnerProfileUpdate(
            name=name, business_name=business_name, phone=phone,
            services=parsed_services, availability=[] # availability will be validated separately
        )
        # Convert services to Pydantic objects for validation
        [schemas.Service(**s) for s in parsed_services]

        parsed_availability = json.loads(availability_json)
        # Convert availability to Pydantic objects for validation
        for day_data in parsed_availability:
            schemas.DailyAvailability(**day_data)

    except (json.JSONDecodeError, ValueError) as e:
        request.session["flash_message"] = _(f"Invalid services or availability data: {e}")
        return RedirectResponse(url="/profile", status_code=status.HTTP_303_SEE_OTHER)

    owner_update = schemas.OwnerProfileUpdate(
        name=name,
        business_name=business_name,
        phone=phone,
        services=parsed_services,
        availability=parsed_availability
    )

    current_owner.name = owner_update.name
    current_owner.business_name = owner_update.business_name
    current_owner.phone = owner_update.phone
    current_owner.services_json = services_json
    current_owner.availability_json = availability_json

    db.add(current_owner)
    db.commit()
    db.refresh(current_owner)

    request.session["flash_message"] = _("Profile updated successfully!")
    return RedirectResponse(url="/profile", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/bookslot/{owner_slug}", response_class=HTMLResponse)
async def get_booking_page(request: Request, owner_slug: str, db: Session = Depends(get_db)):
    jinja_env = get_jinja_env_with_locale(request)
    _ = request.state.gettext
    owner = crud.get_owner_by_slug(db, slug=owner_slug)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Booking page not found"))

    services = json.loads(owner.services_json) if owner.services_json else []
    availability = json.loads(owner.availability_json) if owner.availability_json else []

    return jinja_env.get_template("booking_page.html").render({
        "request": request,
        "owner": owner,
        "services": services,
        "availability": availability,
        "flash_message": request.session.pop("flash_message", None),
        "today_date": date.today().isoformat(),
        "_": _
    })

@app.post("/bookslot/{owner_slug}", response_class=HTMLResponse)
async def submit_booking(
    request: Request,
    owner_slug: str,
    customer_name: str = Form(...),
    customer_email: str = Form(...),
    customer_phone: Optional[str] = Form(None),
    service_name: str = Form(...),
    booking_date: date = Form(...),
    booking_time: str = Form(...),
    db: Session = Depends(get_db)
):
    jinja_env = get_jinja_env_with_locale(request)
    _ = request.state.gettext

    owner = crud.get_owner_by_slug(db, slug=owner_slug)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Booking page not found"))

    # Basic validation (more comprehensive validation would check availability, service existence, etc.)
    if not customer_name or not customer_email or not service_name or not booking_date or not booking_time:
        request.session["flash_message"] = _("All required fields must be filled.")
        return jinja_env.get_template("booking_page.html").render({
            "request": request, "owner": owner, "flash_message": request.session.pop("flash_message", None), "_": _
        })

    booking_data = schemas.BookingCreate(
        customer_name=customer_name,
        customer_email=customer_email,
        customer_phone=customer_phone,
        service_name=service_name,
        booking_date=booking_date,
        booking_time=booking_time
    )

    try:
        db_booking = crud.create_booking(db=db, booking=booking_data, owner_id=owner.id)

        # Send notifications
        # Owner notification
        owner_subject = _("New Booking for {}").format(owner.business_name)
        owner_body = _("You have a new booking from {} for {} on {} at {}. Customer Email: {}. Customer Phone: {}").format(
            customer_name, service_name, booking_date, booking_time, customer_email, customer_phone or _("N/A")
        )
        notifications.send_email(owner.email, owner_subject, owner_body)
        if owner.phone:
            notifications.send_whatsapp_message(owner.phone, owner_body)

        # Customer confirmation
        customer_subject = _("Your Booking Confirmation with {}").format(owner.business_name)
        customer_body = _("Hi {},\n\nYour booking for {} with {} on {} at {} has been confirmed.\n\nThank you!").format(
            customer_name, service_name, owner.business_name, booking_date, booking_time
        )
        notifications.send_email(customer_email, customer_subject, customer_body)
        if customer_phone:
            notifications.send_whatsapp_message(customer_phone, customer_body)

        return jinja_env.get_template("booking_confirmation.html").render({
            "request": request,
            "owner": owner,
            "booking": db_booking,
            "flash_message": request.session.pop("flash_message", None),
            "_": _
        })

    except Exception as e:
        db.rollback()
        request.session["flash_message"] = _(f"An error occurred during booking: {e}")
        return jinja_env.get_template("booking_page.html").render({
            "request": request, "owner": owner, "flash_message": request.session.pop("flash_message", None), "_": _
        })
