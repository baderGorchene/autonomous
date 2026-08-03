from fastapi import FastAPI, Depends, Request, Response, status, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from . import models, schemas, crud, security, dependencies, notifications
from .database import engine, get_db, create_tables
from .i18n_config import get_jinja_templates
from starlette.middleware.sessions import SessionMiddleware
from starlette.routing import Mount
from starlette.staticfiles import StaticFiles
import os
import logging
from .config import settings
import gettext

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create tables if they don't exist
models.Base.metadata.create_all(bind=engine)

app = FastAPI()

# Add Session Middleware for language selection
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

# Static files setup (assuming 'static' folder is at the project root)
STATIC_DIR = os.path.join(settings.PROJECT_ROOT, 'static')
if not os.path.exists(STATIC_DIR):
    os.makedirs(STATIC_DIR)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Middleware to set language
@app.middleware("http")
async def add_i18n_middleware(request: Request, call_next):
    lang = request.session.get("lang", "en")
    
    # Check for language query parameter and update session
    query_lang = request.query_params.get("lang")
    if query_lang and query_lang in ["en", "ar", "fr"]:
        lang = query_lang
        request.session["lang"] = lang
        # Redirect to clean the URL if lang param was used
        redirect_url = str(request.url.remove_query_params(keys=["lang"]))
        response = RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)
        response.set_cookie(key="lang", value=lang) # Also set cookie for client-side use if needed
        return response

    # Check for language cookie
    cookie_lang = request.cookies.get("lang")
    if cookie_lang and cookie_lang in ["en", "ar", "fr"]:
        lang = cookie_lang
        request.session["lang"] = lang

    request.state.lang = lang
    response = await call_next(request)
    return response

# Dependency to get Jinja2Templates instance with current locale
def get_templates_env(request: Request):
    return get_jinja_templates(request.state.lang)

# Health check endpoint
@app.get("/health", response_class=HTMLResponse)
async def health_check():
    return "<h1>BookSlot Health Check: OK</h1>"

# Root redirect to signup for now
@app.get("/", response_class=RedirectResponse, include_in_schema=False)
async def root():
    return RedirectResponse(url="/signup")

# --- Authentication and Owner Management ---
@app.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request, templates: Jinja2Templates = Depends(get_templates_env)):
    return templates.TemplateResponse("signup.html", {"request": request})

@app.post("/signup", response_class=HTMLResponse)
async def signup(request: Request, db: Session = Depends(get_db), templates: Jinja2Templates = Depends(get_templates_env)):
    form_data = await request.form()
    owner_create = schemas.OwnerCreate(
        name=form_data.get("name"),
        email=form_data.get("email"),
        password=form_data.get("password"),
        business_name=form_data.get("business_name"),
        slug=form_data.get("slug"),
        phone=form_data.get("phone") # Added phone number
    )
    
    # Basic validation
    if not owner_create.name or not owner_create.email or not owner_create.password or not owner_create.business_name or not owner_create.slug or not owner_create.phone:
        return templates.TemplateResponse("signup.html", {"request": request, "error": _("All fields are required.")})

    if crud.get_owner_by_email(db, email=owner_create.email):
        return templates.TemplateResponse("signup.html", {"request": request, "error": _("Email already registered.")})
    if crud.get_owner_by_slug(db, slug=owner_create.slug):
        return templates.TemplateResponse("signup.html", {"request": request, "error": _("Business URL slug already taken.")})

    try:
        db_owner = crud.create_owner(db=db, owner=owner_create)
        # Automatically log in the user after signup
        access_token = security.create_access_token(data={"sub": db_owner.email})
        response = RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
        response.set_cookie(key="access_token", value=access_token, httponly=True)
        return response
    except Exception as e:
        logger.error(f"Error during owner signup: {e}")
        return templates.TemplateResponse("signup.html", {"request": request, "error": _("An unexpected error occurred. Please try again.")})

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, templates: Jinja2Templates = Depends(get_templates_env)):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/token")
async def login_for_access_token(request: Request, db: Session = Depends(get_db), templates: Jinja2Templates = Depends(get_templates_env)):
    form_data = await request.form()
    email = form_data.get("username") # OAuth2 spec uses username
    password = form_data.get("password")

    if not email or not password:
        return templates.TemplateResponse("login.html", {"request": request, "error": _("Email and password are required.")})

    owner = crud.authenticate_owner(db, email, password)
    if not owner:
        return templates.TemplateResponse("login.html", {"request": request, "error": _("Incorrect email or password.")})
    
    access_token = security.create_access_token(data={"sub": owner.email})
    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    response.set_cookie(key="access_token", value=access_token, httponly=True)
    return response

@app.get("/logout", response_class=RedirectResponse)
async def logout():
    response = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    response.delete_cookie(key="access_token")
    return response

# --- Dashboard and Profile Management ---
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(
    request: Request, 
    current_owner: schemas.Owner = Depends(dependencies.get_current_owner), 
    db: Session = Depends(get_db),
    templates: Jinja2Templates = Depends(get_templates_env)
):
    bookings = crud.get_owner_bookings(db, current_owner.id)
    return templates.TemplateResponse("dashboard.html", {"request": request, "owner": current_owner, "bookings": bookings})

@app.post("/dashboard/profile", response_class=HTMLResponse)
async def update_profile(
    request: Request,
    current_owner: schemas.Owner = Depends(dependencies.get_current_owner),
    db: Session = Depends(get_db),
    templates: Jinja2Templates = Depends(get_templates_env)
):
    form_data = await request.form()
    owner_update = schemas.OwnerProfileUpdate(
        name=form_data.get("name"),
        business_name=form_data.get("business_name"),
        phone=form_data.get("phone")
    )
    
    if not owner_update.name or not owner_update.business_name or not owner_update.phone:
        bookings = crud.get_owner_bookings(db, current_owner.id)
        return templates.TemplateResponse("dashboard.html", {"request": request, "owner": current_owner, "bookings": bookings, "error": _("All profile fields are required.")})

    try:
        updated_owner = crud.update_owner_profile(db, current_owner, owner_update)
        bookings = crud.get_owner_bookings(db, updated_owner.id)
        return templates.TemplateResponse("dashboard.html", {"request": request, "owner": updated_owner, "bookings": bookings, "message": _("Profile updated successfully!")})
    except Exception as e:
        logger.error(f"Error updating owner profile: {e}")
        bookings = crud.get_owner_bookings(db, current_owner.id)
        return templates.TemplateResponse("dashboard.html", {"request": request, "owner": current_owner, "bookings": bookings, "error": _("An unexpected error occurred. Please try again.")})

# --- Public Booking Page ---
@app.get("/bookslot.app/{owner_slug}", response_class=HTMLResponse)
async def public_booking_page(
    owner_slug: str,
    request: Request,
    db: Session = Depends(get_db),
    templates: Jinja2Templates = Depends(get_templates_env)
):
    owner = crud.get_owner_by_slug(db, slug=owner_slug)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Booking page not found."))
    
    # Placeholder for services and availability - in a real app, these would be retrieved from owner.services_json, owner.availability_json
    services = [
        {"id": 1, "name": _("Haircut"), "duration": 30, "price": 25},
        {"id": 2, "name": _("Coloring"), "duration": 90, "price": 80},
    ]
    
    # Example availability (simplified)
    availability = {
        "Monday": ["09:00", "10:00", "11:00", "14:00", "15:00"],
        "Tuesday": ["09:00", "10:00", "11:00", "14:00", "15:00"],
        "Wednesday": ["09:00", "10:00", "11:00", "14:00", "15:00"],
    }

    return templates.TemplateResponse(
        "booking_page.html",
        {"request": request, "owner": owner, "services": services, "availability": availability}
    )

@app.post("/bookslot.app/{owner_slug}/book", response_class=HTMLResponse)
async def submit_booking(
    owner_slug: str,
    request: Request,
    db: Session = Depends(get_db),
    templates: Jinja2Templates = Depends(get_templates_env)
):
    owner = crud.get_owner_by_slug(db, slug=owner_slug)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Booking page not found."))

    form_data = await request.form()
    
    # Convert form data to BookingCreate schema
    try:
        booking_create = schemas.BookingCreate(
            customer_name=form_data.get("customer_name"),
            customer_email=form_data.get("customer_email"),
            customer_phone=form_data.get("customer_phone"),
            service_name=form_data.get("service_name"),
            booking_date=form_data.get("booking_date"),
            booking_time=form_data.get("booking_time"),
            notes=form_data.get("notes", "")
        )
    except Exception as e:
        logger.error(f"Pydantic validation error for booking: {e}")
        # Re-render the booking page with error
        services = [ # Re-add services and availability for rendering
            {"id": 1, "name": _("Haircut"), "duration": 30, "price": 25},
            {"id": 2, "name": _("Coloring"), "duration": 90, "price": 80},
        ]
        availability = {
            "Monday": ["09:00", "10:00", "11:00", "14:00", "15:00"],
            "Tuesday": ["09:00", "10:00", "11:00", "14:00", "15:00"],
            "Wednesday": ["09:00", "10:00", "11:00", "14:00", "15:00"],
        }
        return templates.TemplateResponse(
            "booking_page.html",
            {"request": request, "owner": owner, "services": services, "availability": availability, "error": _("Please fill in all required booking details correctly.")}
        )

    try:
        db_booking = crud.create_booking(db=db, booking=booking_create, owner_id=owner.id)

        # Send notifications
        notifications.send_owner_notification(
            owner_email=owner.email,
            owner_phone=owner.phone,
            customer_name=db_booking.customer_name,
            service_name=db_booking.service_name,
            booking_date=db_booking.booking_date,
            booking_time=db_booking.booking_time,
            language=request.state.lang
        )
        notifications.send_customer_confirmation(
            customer_email=db_booking.customer_email,
            customer_phone=db_booking.customer_phone,
            owner_name=owner.name,
            business_name=owner.business_name,
            service_name=db_booking.service_name,
            booking_date=db_booking.booking_date,
            booking_time=db_booking.booking_time,
            language=request.state.lang
        )

        return templates.TemplateResponse(
            "booking_confirmation.html",
            {"request": request, "booking": db_booking, "owner": owner}
        )
    except Exception as e:
        logger.error(f"Error creating booking or sending notification: {e}")
        # Re-render the booking page with error
        services = [ # Re-add services and availability for rendering
            {"id": 1, "name": _("Haircut"), "duration": 30, "price": 25},
            {"id": 2, "name": _("Coloring"), "duration": 90, "price": 80},
        ]
        availability = {
            "Monday": ["09:00", "10:00", "11:00", "14:00", "15:00"],
            "Tuesday": ["09:00", "10:00", "11:00", "14:00", "15:00"],
            "Wednesday": ["09:00", "10:00", "11:00", "14:00", "15:00"],
        }
        return templates.TemplateResponse(
            "booking_page.html",
            {"request": request, "owner": owner, "services": services, "availability": availability, "error": _("An unexpected error occurred during booking. Please try again.")}
        )

# Gettext for Jinja2 templates (global access for _ function in routes)
_ = gettext.gettext
