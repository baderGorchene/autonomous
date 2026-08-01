from fastapi import FastAPI, Depends, HTTPException, status, Request, Form, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
import json
import logging
import datetime

from src import crud, models, schemas, security, notifications
from src.database import SessionLocal, engine, create_tables, get_db
from src.config import settings
from src.i18n_config import get_jinja_env

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create database tables on startup
create_tables()

app = FastAPI()

# Dependency to get the current owner
def get_current_owner(token: str = Depends(security.oauth2_scheme), db: Session = Depends(get_db)):
    token_data = security.decode_access_token(token)
    owner = crud.get_owner_by_email(db, email=token_data.email)
    if owner is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Owner not found")
    return owner

# Dependency for Jinja2 environment with i18n
def get_template_env(request: Request):
    locale = request.cookies.get("lang", "en")
    return get_jinja_env(locale)

@app.middleware("http")
async def add_language_cookie_if_missing(request: Request, call_next):
    if "lang" not in request.cookies:
        response = await call_next(request)
        response.set_cookie(key="lang", value="en", httponly=True, max_age=3600 * 24 * 30) # 30 days
        return response
    response = await call_next(request)
    return response

@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request, env = Depends(get_template_env)):
    template = env.get_template("home.html") # Assuming a simple home page
    return template.render(request=request)

@app.get("/signup", response_class=HTMLResponse)
async def signup_form(request: Request, env = Depends(get_template_env)):
    template = env.get_template("signup.html")
    return template.render(request=request, error_message=None)

@app.post("/signup", response_class=HTMLResponse)
async def signup_owner(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    business_name: str = Form(...),
    slug: str = Form(...),
    phone: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    env = Depends(get_template_env)
):
    owner = crud.get_owner_by_email(db, email=email)
    if owner:
        template = env.get_template("signup.html")
        return template.render(request=request, error_message="Email already registered")
    
    owner_by_slug = crud.get_owner_by_slug(db, slug=slug)
    if owner_by_slug:
        template = env.get_template("signup.html")
        return template.render(request=request, error_message="Business URL already taken")

    try:
        owner_data = schemas.OwnerCreate(
            name=name, email=email, password=password,
            business_name=business_name, slug=slug, phone=phone
        )
        db_owner = crud.create_owner(db=db, owner=owner_data)
    except Exception as e:
        logger.error(f"Error creating owner: {e}")
        template = env.get_template("signup.html")
        return template.render(request=request, error_message="An error occurred during signup. Please try again.")

    response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    return response

@app.get("/login", response_class=HTMLResponse)
async def login_form(request: Request, env = Depends(get_template_env)):
    template = env.get_template("login.html")
    return template.render(request=request, error_message=None)

@app.post("/token", response_model=schemas.Token)
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    owner = crud.authenticate_owner(db, form_data.username, form_data.password)
    if not owner:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = security.create_access_token(data={"sub": owner.email})
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/login", response_class=HTMLResponse)
async def login_owner(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
    env = Depends(get_template_env)
):
    owner = crud.authenticate_owner(db, email, password)
    if not owner:
        template = env.get_template("login.html")
        return template.render(request=request, error_message="Incorrect email or password")
    
    access_token = security.create_access_token(data={"sub": owner.email})
    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(key="access_token", value=access_token, httponly=True, max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60)
    return response

@app.get("/logout")
async def logout(response: Response):
    response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie("access_token")
    return response

@app.get("/dashboard", response_class=HTMLResponse)
async def owner_dashboard(
    request: Request,
    current_owner: models.Owner = Depends(get_current_owner),
    db: Session = Depends(get_db),
    env = Depends(get_template_env)
):
    bookings = crud.get_owner_bookings(db, current_owner.id)
    services = json.loads(current_owner.services_json) if current_owner.services_json else []
    availability = json.loads(current_owner.availability_json) if current_owner.availability_json else {}

    template = env.get_template("dashboard.html")
    return template.render(
        request=request,
        owner=current_owner,
        bookings=bookings,
        services=services,
        availability=availability,
        error_message=None,
        success_message=None
    )

@app.post("/dashboard/profile", response_class=HTMLResponse)
async def update_owner_profile(
    request: Request,
    name: str = Form(...),
    business_name: str = Form(...),
    phone: Optional[str] = Form(None),
    services_data: str = Form(...), # JSON string
    availability_data: str = Form(...), # JSON string
    current_owner: models.Owner = Depends(get_current_owner),
    db: Session = Depends(get_db),
    env = Depends(get_template_env)
):
    error_message = None
    success_message = None

    try:
        # Validate services_data
        parsed_services = json.loads(services_data)
        validated_services = [schemas.Service(**s) for s in parsed_services]
        current_owner.services_json = json.dumps([s.dict() for s in validated_services])
        
        # Validate availability_data
        parsed_availability = json.loads(availability_data)
        # Ensure the root is a dict for Availability schema
        validated_availability = schemas.Availability(__root__=parsed_availability) 
        current_owner.availability_json = json.dumps(validated_availability.dict()['__root__'])

        owner_update = schemas.OwnerProfileUpdate(
            name=name,
            business_name=business_name,
            phone=phone
        )
        crud.update_owner_profile(db, current_owner, owner_update)
        success_message = env.get_template("dashboard.html").environment.gettext("Profile updated successfully!")

    except json.JSONDecodeError:
        error_message = env.get_template("dashboard.html").environment.gettext("Invalid JSON format for services or availability.")
    except Exception as e:
        logger.error(f"Error updating owner profile: {e}")
        error_message = env.get_template("dashboard.html").environment.gettext(f"An error occurred: {e}")

    # Re-fetch data for rendering the dashboard
    bookings = crud.get_owner_bookings(db, current_owner.id)
    services = json.loads(current_owner.services_json) if current_owner.services_json else []
    availability = json.loads(current_owner.availability_json) if current_owner.availability_json else {}

    template = env.get_template("dashboard.html")
    return template.render(
        request=request,
        owner=current_owner,
        bookings=bookings,
        services=services,
        availability=availability,
        error_message=error_message,
        success_message=success_message
    )


@app.get("/bookslot.app/{slug}", response_class=HTMLResponse)
async def public_booking_page(
    request: Request,
    slug: str,
    env = Depends(get_template_env),
    db: Session = Depends(get_db),
    error_message: Optional[str] = None, # For re-rendering with errors
    success_message: Optional[str] = None
):
    owner = crud.get_owner_by_slug(db, slug=slug)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking page not found")
    
    services = json.loads(owner.services_json) if owner.services_json else []
    availability = json.loads(owner.availability_json) if owner.availability_json else {}

    template = env.get_template("booking_page.html")
    return template.render(
        request=request,
        owner=owner,
        services=services,
        availability=availability,
        error_message=error_message,
        success_message=success_message
    )

@app.post("/bookslot.app/{slug}/book", response_class=HTMLResponse)
async def submit_booking(
    request: Request,
    slug: str,
    customer_name: str = Form(...),
    customer_email: str = Form(...),
    customer_phone: Optional[str] = Form(None),
    service_name: str = Form(...),
    booking_date: str = Form(...), # YYYY-MM-DD
    booking_time: str = Form(...), # HH:MM AM/PM
    db: Session = Depends(get_db),
    env = Depends(get_template_env)
):
    owner = crud.get_owner_by_slug(db, slug=slug)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking page not found")

    try:
        parsed_booking_date = datetime.datetime.strptime(booking_date, "%Y-%m-%d").date()
        
        booking_data = schemas.BookingCreate(
            customer_name=customer_name,
            customer_email=customer_email,
            customer_phone=customer_phone,
            service_name=service_name,
            booking_date=parsed_booking_date,
            booking_time=booking_time
        )
        
        db_booking = crud.create_booking(db=db, booking=booking_data, owner_id=owner.id)
        
        # Send notifications
        notifications.notify_new_booking(db_owner=owner, booking=booking_data)

        template = env.get_template("booking_confirmation.html")
        return template.render(request=request, booking=db_booking, owner=owner)

    except ValueError:
        error_message = env.get_template("booking_page.html").environment.gettext("Invalid date or time format.")
        return await public_booking_page(request, slug, env, db, error_message=error_message)
    except Exception as e:
        logger.error(f"Error submitting booking for slug {slug}: {e}")
        error_message = env.get_template("booking_page.html").environment.gettext("An error occurred during booking. Please try again.")
        return await public_booking_page(request, slug, env, db, error_message=error_message)

@app.get("/set_lang/{lang_code}")
async def set_language(lang_code: str, response: Response, request: Request):
    response = RedirectResponse(url=request.headers.get("referer", "/"), status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(key="lang", value=lang_code, httponly=True, max_age=3600 * 24 * 30) # 30 days
    return response
