from fastapi import FastAPI, Depends, HTTPException, status, Request, Response, Form
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
import datetime
import json
import gettext
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import JSONResponse
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

from . import crud, models, schemas, security, notifications
from .database import engine, SessionLocal
from .config import settings
from .i18n_config import get_jinja_env # Ensure this is correct

models.Base.metadata.create_all(bind=engine)

app = FastAPI()

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Add SessionMiddleware for language handling
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Helper to get Jinja2 environment with current locale
def get_jinja_env_with_locale(request: Request):
    locale = request.session.get('lang', 'en')
    return get_jinja_env(locale)

@app.get("/health", tags=["Health Check"])
async def health_check():
    return {"status": "ok"}

@app.get("/", response_class=HTMLResponse)
async def root(request: Request, db: Session = Depends(get_db)):
    env = get_jinja_env_with_locale(request)
    _ = env.gettext
    return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

@app.get("/lang/{lang_code}")
async def set_language(lang_code: str, request: Request):
    request.session['lang'] = lang_code
    # Redirect back to the page where the language was changed
    # For simplicity, redirecting to root or a default page
    referer = request.headers.get("referer")
    if referer:
        return RedirectResponse(url=referer, status_code=status.HTTP_302_FOUND)
    return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)

@app.post("/token", response_model=schemas.Token, tags=["Authentication"])
async def login_for_access_token(request: Request, response: Response, db: Session = Depends(get_db), form_data: OAuth2PasswordRequestForm = Depends()):
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
    response.set_cookie(key="access_token", value=access_token, httponly=True, samesite="lax", secure=True)
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/login", response_class=HTMLResponse, tags=["Authentication"])
async def login_page(request: Request):
    env = get_jinja_env_with_locale(request)
    template = env.get_template("login.html")
    _ = env.gettext
    return template.render(request=request, _=_)

@app.post("/login", response_class=HTMLResponse, tags=["Authentication"])
async def handle_login(request: Request, response: Response, db: Session = Depends(get_db), email: str = Form(...), password: str = Form(...)):
    owner = security.authenticate_owner(db, email, password)
    if not owner:
        env = get_jinja_env_with_locale(request)
        template = env.get_template("login.html")
        _ = env.gettext
        return template.render(request=request, error=_("Incorrect email or password"), _=_)

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": owner.email}, expires_delta=access_token_expires
    )
    response.set_cookie(key="access_token", value=access_token, httponly=True, samesite="lax", secure=True)
    return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)

@app.get("/register", response_class=HTMLResponse, tags=["Authentication"])
async def register_page(request: Request):
    env = get_jinja_env_with_locale(request)
    template = env.get_template("register.html")
    _ = env.gettext
    return template.render(request=request, _=_)

@app.post("/register", response_class=HTMLResponse, tags=["Authentication"])
async def handle_register(request: Request, db: Session = Depends(get_db),
                          name: str = Form(...), email: str = Form(...), password: str = Form(...),
                          business_name: str = Form(...), slug: str = Form(...)):
    db_owner = crud.get_owner_by_email(db, email=email)
    if db_owner:
        env = get_jinja_env_with_locale(request)
        template = env.get_template("register.html")
        _ = env.gettext
        return template.render(request=request, error=_("Email already registered"), _=_)
    
    db_owner = crud.get_owner_by_slug(db, slug=slug)
    if db_owner:
        env = get_jinja_env_with_locale(request)
        template = env.get_template("register.html")
        _ = env.gettext
        return template.render(request=request, error=_("Business URL (slug) already taken"), _=_)

    owner_create = schemas.OwnerCreate(name=name, email=email, password=password, business_name=business_name, slug=slug)
    crud.create_owner(db=db, owner=owner_create)
    return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

@app.get("/dashboard", response_class=HTMLResponse, tags=["Owner Dashboard"])
async def dashboard(request: Request, db: Session = Depends(get_db), current_owner: models.Owner = Depends(security.get_current_owner)):
    env = get_jinja_env_with_locale(request)
    template = env.get_template("dashboard.html")
    _ = env.gettext
    
    upcoming_bookings = db.query(models.Booking).filter(
        models.Booking.owner_id == current_owner.id,
        models.Booking.booking_date >= datetime.date.today()
    ).order_by(models.Booking.booking_date, models.Booking.booking_time).all()

    # Deserialize services and availability
    services = json.loads(current_owner.services_json) if current_owner.services_json else []
    availability = json.loads(current_owner.availability_json) if current_owner.availability_json else {}

    return template.render(
        request=request, 
        owner=current_owner, 
        bookings=upcoming_bookings,
        services=services,
        availability=availability,
        _=_,
        current_lang=request.session.get('lang', 'en')
    )

@app.post("/dashboard/profile", response_class=HTMLResponse, tags=["Owner Dashboard"])
async def update_profile(request: Request, db: Session = Depends(get_db),
                         current_owner: models.Owner = Depends(security.get_current_owner),
                         name: str = Form(...), business_name: str = Form(...), phone: Optional[str] = Form(None),
                         services_json: str = Form(...), availability_json: str = Form(...)):
    env = get_jinja_env_with_locale(request)
    _ = env.gettext
    try:
        # Validate services_json and availability_json
        services_data = json.loads(services_json)
        availability_data = json.loads(availability_json)
        
        # Optional: further validation with Pydantic schemas if needed
        schemas.OwnerProfileUpdate(
            name=name,
            business_name=business_name,
            phone=phone,
            services=[schemas.Service(**s) for s in services_data],
            availability=[schemas.Availability(**a) for a in availability_data]
        )

        owner_update = schemas.OwnerProfileUpdate(
            name=name, business_name=business_name, phone=phone,
            services=[schemas.Service(**s) for s in services_data],
            availability=[schemas.Availability(**a) for a in availability_data]
        )
        
        current_owner.name = owner_update.name
        current_owner.business_name = owner_update.business_name
        current_owner.phone = owner_update.phone
        current_owner.services_json = services_json
        current_owner.availability_json = availability_json

        db.add(current_owner)
        db.commit()
        db.refresh(current_owner)
        return RedirectResponse(url="/dashboard?success=profile_updated", status_code=status.HTTP_302_FOUND)
    except json.JSONDecodeError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_("Invalid JSON for services or availability."))
    except Exception as e:
        # Log the error for debugging
        print(f"Error updating profile: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=_("An error occurred while updating your profile."))

@app.get("/book/{owner_slug}", response_class=HTMLResponse, tags=["Public Booking"])
async def booking_page(owner_slug: str, request: Request, db: Session = Depends(get_db)):
    env = get_jinja_env_with_locale(request)
    template = env.get_template("booking_page.html")
    _ = env.gettext
    
    owner = crud.get_owner_by_slug(db, slug=owner_slug)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Owner not found"))
    
    services = json.loads(owner.services_json) if owner.services_json else []
    availability = json.loads(owner.availability_json) if owner.availability_json else {}

    # For simplicity, calculate available dates/times here or in JS
    # This is a basic example, real availability logic would be more complex
    available_slots = {"2023-12-25": ["09:00", "10:00"], "2023-12-26": ["11:00", "12:00"]}

    return template.render(
        request=request,
        owner=owner,
        services=services,
        availability=availability,
        available_slots=available_slots,
        _=_,
        current_lang=request.session.get('lang', 'en')
    )

@app.post("/book/{owner_slug}/submit", response_class=HTMLResponse, tags=["Public Booking"])
async def submit_booking(owner_slug: str, request: Request, db: Session = Depends(get_db),
                         customer_name: str = Form(...), customer_email: str = Form(...),
                         customer_phone: Optional[str] = Form(None), service_name: str = Form(...),
                         booking_date_str: str = Form(...), booking_time: str = Form(...)):
    env = get_jinja_env_with_locale(request)
    _ = env.gettext
    owner = crud.get_owner_by_slug(db, slug=owner_slug)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Owner not found"))
    
    try:
        booking_date = datetime.datetime.strptime(booking_date_str, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_("Invalid date format."))

    # Basic validation (e.g., date in future, time valid)
    if booking_date < datetime.date.today():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_("Cannot book in the past."))
    # More complex validation (e.g., check against owner's availability) would go here

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

        # Send email/WhatsApp notifications
        email_content = notifications.generate_booking_confirmation_email(
            owner_name=owner.name, business_name=owner.business_name, 
            customer_name=customer_name, service_name=service_name,
            booking_date=booking_date_str, booking_time=booking_time,
            owner_email=owner.email, customer_email=customer_email, lang=request.session.get('lang', 'en')
        )

        notifications.send_email_confirmation(
            to_email=customer_email, 
            subject=email_content["customer_subject"],
            html_content=email_content["customer_html"]
        )
        notifications.send_email_confirmation(
            to_email=owner.email, 
            subject=email_content["owner_subject"],
            html_content=email_content["owner_html"]
        )

        if owner.phone:
            notifications.send_whatsapp_confirmation(
                to_phone=owner.phone, 
                message_body=f"New booking for {service_name} from {customer_name} on {booking_date_str} at {booking_time}."
            )
        if customer_phone:
            notifications.send_whatsapp_confirmation(
                to_phone=customer_phone, 
                message_body=f"Hi {customer_name}, your booking for {service_name} with {owner.business_name} on {booking_date_str} at {booking_time} is confirmed."
            )

        template = env.get_template("booking_confirmation.html")
        return template.render(
            request=request,
            owner=owner,
            booking=db_booking,
            _=_,
            current_lang=request.session.get('lang', 'en')
        )
    except Exception as e:
        # Log the error for debugging
        print(f"Error processing booking: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=_("An error occurred while processing your booking."))

