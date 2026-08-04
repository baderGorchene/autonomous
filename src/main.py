from fastapi import FastAPI, Depends, HTTPException, status, Request, Response, Form, APIRouter
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import json
import logging
from typing import Optional, Dict, Any, List

from . import crud, models, schemas, security, dependencies, notifications
from .database import engine, get_db, create_tables
from .config import settings
from .i18n_config import get_jinja_templates, get_templates_env

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

@app.on_event("startup")
def on_startup():
    create_tables()

@app.middleware("http")
async def add_language_middleware(request: Request, call_next):
    lang = request.query_params.get("lang")
    if lang:
        request.state.lang = lang
    else:
        accept_language = request.headers.get("Accept-Language", "en").split(',')[0].lower()
        if 'ar' in accept_language:
            request.state.lang = 'ar'
        elif 'fr' in accept_language:
            request.state.lang = 'fr'
        else:
            request.state.lang = 'en'

    request.state.templates = get_jinja_templates(request.state.lang)
    response = await call_next(request)
    return response

@app.get("/health", response_class=HTMLResponse)
async def health_check():
    return "<h1>BookSlot is healthy!</h1>"

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
async def signup_form(request: Request, templates: Jinja2Templates = Depends(get_templates_env)):
    return templates.TemplateResponse("signup.html", {"request": request})

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
    templates: Jinja2Templates = Depends(get_templates_env)
):
    owner = crud.get_owner_by_email(db, email=email)
    if owner:
        return templates.TemplateResponse("signup.html", {"request": request, "error": "Email already registered"}, status_code=status.HTTP_400_BAD_REQUEST)
    
    owner_by_slug = crud.get_owner_by_slug(db, slug=slug)
    if owner_by_slug:
        return templates.TemplateResponse("signup.html", {"request": request, "error": "Business URL already taken. Please choose another."}, status_code=status.HTTP_400_BAD_REQUEST)

    try:
        owner_create = schemas.OwnerCreate(
            name=name, email=email, password=password, business_name=business_name, slug=slug, phone=phone
        )
        db_owner = crud.create_owner(db=db, owner=owner_create)
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        logger.error(f"Error creating owner: {e}")
        return templates.TemplateResponse("signup.html", {"request": request, "error": f"An error occurred: {e}"}, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, templates: Jinja2Templates = Depends(get_templates_env)):
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/owner/dashboard", response_class=HTMLResponse)
async def owner_dashboard(
    request: Request,
    current_owner: models.Owner = Depends(dependencies.get_current_owner),
    db: Session = Depends(get_db),
    templates: Jinja2Templates = Depends(get_templates_env)
):
    bookings = crud.get_owner_bookings(db, owner_id=current_owner.id)
    services = json.loads(current_owner.services_json) if current_owner.services_json else []
    availability = json.loads(current_owner.availability_json) if current_owner.availability_json else {}

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "owner": current_owner,
            "bookings": bookings,
            "services": services,
            "availability": availability,
            "current_lang": request.state.lang
        }
    )

@app.post("/owner/profile", response_class=HTMLResponse)
async def update_owner_profile_endpoint(
    request: Request,
    name: str = Form(...),
    business_name: str = Form(...),
    phone: Optional[str] = Form(None),
    current_owner: models.Owner = Depends(dependencies.get_current_owner),
    db: Session = Depends(get_db),
    templates: Jinja2Templates = Depends(get_templates_env)
):
    try:
        owner_update = schemas.OwnerProfileUpdate(name=name, business_name=business_name, phone=phone)
        updated_owner = crud.update_owner_profile(db, current_owner, owner_update)
        return RedirectResponse(url="/owner/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        logger.error(f"Error updating owner profile: {e}")
        bookings = crud.get_owner_bookings(db, owner_id=current_owner.id)
        services = json.loads(current_owner.services_json) if current_owner.services_json else []
        availability = json.loads(current_owner.availability_json) if current_owner.availability_json else {}
        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "owner": current_owner,
                "bookings": bookings,
                "services": services,
                "availability": availability,
                "error": f"Failed to update profile: {e}",
                "current_lang": request.state.lang
            },
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@app.get("/{owner_slug}", response_class=HTMLResponse)
async def public_booking_page(
    owner_slug: str,
    request: Request,
    db: Session = Depends(get_db),
    templates: Jinja2Templates = Depends(get_templates_env)
):
    owner = crud.get_owner_by_slug(db, slug=owner_slug)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Owner not found")

    services = json.loads(owner.services_json) if owner.services_json else []
    availability = json.loads(owner.availability_json) if owner.availability_json else {}

    if not services:
        services = [
            {"name": "Haircut", "description": "Standard haircut", "price": 25.00, "duration_minutes": 30},
            {"name": "Coloring", "description": "Full hair coloring", "price": 80.00, "duration_minutes": 90}
        ]
        owner.services_json = json.dumps(services)
        db.add(owner)
        db.commit()
        db.refresh(owner)

    return templates.TemplateResponse(
        "booking_page.html",
        {
            "request": request,
            "owner": owner,
            "services": services,
            "availability": availability,
            "current_lang": request.state.lang,
            "base_url": str(request.base_url)
        }
    )

@app.post("/{owner_slug}/book", response_class=HTMLResponse)
async def submit_booking(
    owner_slug: str,
    request: Request,
    customer_name: str = Form(...),
    customer_email: str = Form(...),
    customer_phone: Optional[str] = Form(None),
    service_name: str = Form(...),
    booking_date_str: str = Form(..., alias="booking_date"),
    booking_time: str = Form(...),
    message: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    templates: Jinja2Templates = Depends(get_templates_env)
):
    owner = crud.get_owner_by_slug(db, slug=owner_slug)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Owner not found")

    try:
        booking_date = datetime.strptime(booking_date_str, '%Y-%m-%d')

        booking_create = schemas.BookingCreate(
            customer_name=customer_name,
            customer_email=customer_email,
            customer_phone=customer_phone,
            service_name=service_name,
            booking_date=booking_date,
            booking_time=booking_time,
            message=message
        )
        db_booking = crud.create_booking(db=db, booking=booking_create, owner_id=owner.id)

        full_booking_page_link = str(request.base_url).rstrip('/') + f"/{owner_slug}"
        notifications.send_booking_confirmation_emails(
            owner_email=owner.email,
            customer_email=db_booking.customer_email,
            booking=db_booking,
            owner_name=owner.name,
            business_name=owner.business_name,
            customer_name=db_booking.customer_name,
            booking_page_link=full_booking_page_link
        )
        notifications.send_new_booking_whatsapp_notification(
            owner_phone=owner.phone,
            booking=db_booking,
            business_name=owner.business_name,
            customer_name=db_booking.customer_name
        )

        return templates.TemplateResponse(
            "booking_confirmation.html",
            {
                "request": request,
                "booking": db_booking,
                "owner": owner,
                "current_lang": request.state.lang
            }
        )
    except ValueError:
        return templates.TemplateResponse(
            "booking_page.html",
            {
                "request": request,
                "owner": owner,
                "services": json.loads(owner.services_json),
                "availability": json.loads(owner.availability_json),
                "error": "Invalid date format. Please use YYYY-MM-DD.",
                "current_lang": request.state.lang
            },
            status_code=status.HTTP_400_BAD_REQUEST
        )
    except Exception as e:
        logger.error(f"Error submitting booking: {e}")
        return templates.TemplateResponse(
            "booking_page.html",
            {
                "request": request,
                "owner": owner,
                "services": json.loads(owner.services_json),
                "availability": json.loads(owner.availability_json),
                "error": f"An unexpected error occurred: {e}",
                "current_lang": request.state.lang
            },
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@app.get("/logout", response_class=RedirectResponse)
async def logout():
    response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(key="access_token")
    return response
