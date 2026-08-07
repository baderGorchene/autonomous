import json
from datetime import date, time, datetime
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException, status, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import Response
from starlette.templating import Jinja2Templates
from starlette.staticfiles import StaticFiles

from . import crud, models, schemas, security, notifications
from .database import SessionLocal, engine, create_tables
from .config import settings
from .i18n import get_locale, setup_i18n, gettext_lazy as _

# Initialize FastAPI app
app = FastAPI()

# Setup Jinja2 templates
templates = Jinja2Templates(directory="templates")

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Session middleware for language selection and potential user sessions (though JWT is used for auth)
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

# Setup i18n
setup_i18n(app, templates)

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# --- Helper functions ---
async def get_current_owner(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = security.decode_access_token(token)
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
        token_data = schemas.TokenData(email=email)
    except Exception:
        raise credentials_exception
    owner = crud.get_owner_by_email(db, email=token_data.email)
    if owner is None:
        raise credentials_exception
    return owner

def get_current_active_owner(current_owner: models.Owner = Depends(get_current_owner)):
    return current_owner

# --- Authentication and User Management ---

@app.on_event("startup")
def on_startup():
    create_tables()

@app.post("/token", response_model=schemas.Token)
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)
):
    owner = crud.authenticate_owner(db, form_data.username, form_data.password)
    if not owner:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = security.timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": owner.email}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse("signup.html", {"request": request, "locale": get_locale(request), "settings": settings})

@app.post("/signup", response_class=HTMLResponse)
async def signup_owner(
    request: Request,
    name: str = Form(...),
    email: EmailStr = Form(...),
    password: str = Form(...),
    business_name: str = Form(...),
    slug: str = Form(...),
    phone: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    try:
        owner = schemas.OwnerCreate(name=name, email=email, password=password, business_name=business_name, slug=slug, phone=phone)
        db_owner = crud.create_owner(db, owner)
        response = RedirectResponse(url="/login?message=signup_success", status_code=status.HTTP_303_SEE_OTHER)
        return response
    except ValueError as e:
        return templates.TemplateResponse("signup.html", {"request": request, "error": str(e), "locale": get_locale(request), "settings": settings}, status_code=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return templates.TemplateResponse("signup.html", {"request": request, "error": _("An unexpected error occurred. Please try again."), "locale": get_locale(request), "settings": settings}, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    message = request.query_params.get("message")
    return templates.TemplateResponse("login.html", {"request": request, "message": message, "locale": get_locale(request), "settings": settings})

@app.post("/login", response_class=HTMLResponse)
async def login_owner(
    request: Request,
    email: EmailStr = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    owner = crud.authenticate_owner(db, email, password)
    if not owner:
        return templates.TemplateResponse("login.html", {"request": request, "error": _("Invalid email or password"), "locale": get_locale(request), "settings": settings}, status_code=status.HTTP_401_UNAUTHORIZED)
    
    access_token_expires = security.timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": owner.email}, expires_delta=access_token_expires
    )
    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(key="access_token", value=access_token, httponly=True, expires=access_token_expires.total_seconds())
    return response

@app.get("/logout")
async def logout(request: Request):
    response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(key="access_token")
    return response

# --- Public Booking Page ---
@app.get("/book/{owner_slug}", response_class=HTMLResponse)
async def booking_page(request: Request, owner_slug: str, db: Session = Depends(get_db)):
    owner = crud.get_owner_by_slug(db, slug=owner_slug)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Booking page not found."))

    try:
        services = json.loads(owner.services_json) if owner.services_json else []
        availability = json.loads(owner.availability_json) if owner.availability_json else {}
    except json.JSONDecodeError:
        services = []
        availability = {}
        print(f"Warning: Malformed JSON for owner {owner.id}")

    return templates.TemplateResponse(
        "booking_page.html",
        {"request": request, "owner": owner, "services": services, "availability": availability, "locale": get_locale(request), "settings": settings}
    )

@app.post("/book/{owner_slug}", response_class=HTMLResponse)
async def submit_booking(
    request: Request,
    owner_slug: str,
    customer_name: str = Form(...),
    customer_email: EmailStr = Form(...),
    customer_phone: Optional[str] = Form(None),
    booking_date: date = Form(...),
    booking_time: time = Form(...),
    service_name: str = Form(...),
    db: Session = Depends(get_db)
):
    owner = crud.get_owner_by_slug(db, slug=owner_slug)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Booking page not found."))
    
    try:
        booking_create = schemas.BookingCreate(
            customer_name=customer_name,
            customer_email=customer_email,
            customer_phone=customer_phone,
            booking_date=booking_date,
            booking_time=booking_time,
            service_name=service_name
        )
        db_booking = crud.create_booking(db=db, booking=booking_create, owner_id=owner.id)

        notifications.send_booking_confirmation_email(db_booking, owner, locale=get_locale(request))
        if owner.phone:
            notifications.send_owner_whatsapp_notification(db_booking, owner, locale=get_locale(request))
        if db_booking.customer_phone:
            notifications.send_customer_whatsapp_notification(db_booking, owner, locale=get_locale(request))

        return templates.TemplateResponse("booking_confirmation.html", {"request": request, "booking": db_booking, "owner": owner, "locale": get_locale(request), "settings": settings})
    except ValueError as e:
        services = json.loads(owner.services_json) if owner.services_json else []
        availability = json.loads(owner.availability_json) if owner.availability_json else {}
        return templates.TemplateResponse(
            "booking_page.html",
            {"request": request, "owner": owner, "services": services, "availability": availability, "error": str(e), "locale": get_locale(request), "settings": settings},
            status_code=status.HTTP_400_BAD_REQUEST
        )
    except Exception as e:
        services = json.loads(owner.services_json) if owner.services_json else []
        availability = json.loads(owner.availability_json) if owner.availability_json else {}
        return templates.TemplateResponse(
            "booking_page.html",
            {"request": request, "owner": owner, "services": services, "availability": availability, "error": _("An unexpected error occurred during booking. Please try again."), "locale": get_locale(request), "settings": settings},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

# --- Owner Dashboard ---
@app.get("/dashboard", response_class=HTMLResponse)
async def owner_dashboard(request: Request, current_owner: models.Owner = Depends(get_current_active_owner), db: Session = Depends(get_db)):
    bookings = crud.get_owner_bookings(db, owner_id=current_owner.id)
    
    try:
        current_owner_services = json.loads(current_owner.services_json) if current_owner.services_json else []
        current_owner_availability = json.loads(current_owner.availability_json) if current_owner.availability_json else {}
    except json.JSONDecodeError:
        current_owner_services = []
        current_owner_availability = {}
        print(f"Warning: Malformed JSON for owner {current_owner.id}")

    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "owner": current_owner, "bookings": bookings, "services": current_owner_services, "availability": current_owner_availability, "locale": get_locale(request), "settings": settings}
    )

@app.post("/dashboard/profile", response_class=HTMLResponse)
async def update_owner_profile_post(
    request: Request,
    name: str = Form(...),
    business_name: str = Form(...),
    phone: Optional[str] = Form(None),
    services_data: str = Form('[]'),
    availability_data: str = Form('{}'),
    current_owner: models.Owner = Depends(get_current_active_owner),
    db: Session = Depends(get_db)
):
    try:
        json.loads(services_data)
        json.loads(availability_data)

        owner_update = schemas.OwnerProfileUpdate(
            name=name,
            business_name=business_name,
            phone=phone,
            services_json=services_data,
            availability_json=availability_data
        )
        updated_owner = crud.update_owner_profile(db, current_owner, owner_update)
        bookings = crud.get_owner_bookings(db, owner_id=updated_owner.id)
        current_owner_services = json.loads(updated_owner.services_json) if updated_owner.services_json else []
        current_owner_availability = json.loads(updated_owner.availability_json) if updated_owner.availability_json else {}
        return templates.TemplateResponse(
            "dashboard.html",
            {"request": request, "owner": updated_owner, "bookings": bookings, "services": current_owner_services, "availability": current_owner_availability, "success_message": _("Profile updated successfully!"), "locale": get_locale(request), "settings": settings}
        )
    except json.JSONDecodeError:
        bookings = crud.get_owner_bookings(db, owner_id=current_owner.id)
        current_owner_services = json.loads(current_owner.services_json) if current_owner.services_json else []
        current_owner_availability = json.loads(current_owner.availability_json) if current_owner.availability_json else {}
        return templates.TemplateResponse(
            "dashboard.html",
            {"request": request, "owner": current_owner, "bookings": bookings, "services": current_owner_services, "availability": current_owner_availability, "error": _("Invalid JSON format for services or availability. Please check your input."), "locale": get_locale(request), "settings": settings},
            status_code=status.HTTP_400_BAD_REQUEST
        )
    except Exception as e:
        bookings = crud.get_owner_bookings(db, owner_id=current_owner.id)
        current_owner_services = json.loads(current_owner.services_json) if current_owner.services_json else []
        current_owner_availability = json.loads(current_owner.availability_json) if current_owner.availability_json else {}
        return templates.TemplateResponse(
            "dashboard.html",
            {"request": request, "owner": current_owner, "bookings": bookings, "services": current_owner_services, "availability": current_owner_availability, "error": _("An unexpected error occurred during profile update. Please try again."), "locale": get_locale(request), "settings": settings},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

# --- Root endpoint ---
@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "locale": get_locale(request), "settings": settings})

# --- Health check endpoint ---
@app.get("/health")
async def health_check():
    return {"status": "ok"}

# --- Language toggle endpoint ---
@app.get("/toggle-lang/{lang_code}")
async def toggle_language(request: Request, lang_code: str):
    response = RedirectResponse(url=request.headers.get("referer", "/"), status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(key="locale", value=lang_code, max_age=30*24*60*60) # Set cookie for 30 days
    return response
