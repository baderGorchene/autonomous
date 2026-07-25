from fastapi import FastAPI, Depends, HTTPException, status, Request, Form, Response
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import timedelta, datetime
import json
import os
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

from . import models, schemas, crud, security, notifications
from .database import SessionLocal, engine
from .config import settings
from .i18n_config import get_jinja_env
from fastapi.staticfiles import StaticFiles

# Create database tables
models.Base.metadata.create_all(bind=engine)

app = FastAPI()

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# OAuth2PasswordBearer for token authentication
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Dependency to get current owner
async def get_current_owner(request: Request, db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    token = request.cookies.get("access_token")
    if not token:
        raise credentials_exception
    token_data = security.verify_token(token, credentials_exception)
    owner = crud.get_owner_by_email(db, email=token_data.email)
    if owner is None:
        raise credentials_exception
    return owner

# Helper to get Jinja2Templates with i18n support
def get_templates(request: Request):
    lang = request.query_params.get("lang", "en")
    env = get_jinja_env(locale=lang)
    return Jinja2Templates(env=env)

# --- Routes ---

@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request, templates: Jinja2Templates = Depends(get_templates)):
    access_token = request.cookies.get("access_token")
    if access_token:
        try:
            security.verify_token(access_token, HTTPException(status_code=401))
            return RedirectResponse(url="/dashboard?lang=" + request.query_params.get("lang", "en"), status_code=status.HTTP_302_FOUND)
        except HTTPException:
            pass
    return templates.TemplateResponse("login.html", {"request": request, "lang": request.query_params.get("lang", "en")})

@app.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request, templates: Jinja2Templates = Depends(get_templates)):
    return templates.TemplateResponse("signup.html", {"request": request, "lang": request.query_params.get("lang", "en")})

@app.post("/signup", response_class=HTMLResponse)
async def signup_owner(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    business_name: str = Form(...),
    slug: str = Form(...),
    db: Session = Depends(get_db),
    templates: Jinja2Templates = Depends(get_templates)
):
    existing_owner = crud.get_owner_by_email(db, email=email)
    if existing_owner:
        return templates.TemplateResponse("signup.html", {"request": request, "error": "Email already registered", "lang": request.query_params.get("lang", "en")})
    existing_slug = crud.get_owner_by_slug(db, slug=slug)
    if existing_slug:
        return templates.TemplateResponse("signup.html", {"request": request, "error": "Booking page URL slug already taken", "lang": request.query_params.get("lang", "en")})

    owner_in = schemas.OwnerCreate(name=name, email=email, password=password, business_name=business_name, slug=slug)
    crud.create_owner(db=db, owner=owner_in)
    return RedirectResponse(url="/login?lang=" + request.query_params.get("lang", "en"), status_code=status.HTTP_302_FOUND)

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, templates: Jinja2Templates = Depends(get_templates)):
    return templates.TemplateResponse("login.html", {"request": request, "lang": request.query_params.get("lang", "en")})

@app.post("/login", response_class=HTMLResponse)
async def login_for_access_token(
    request: Request,
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
    templates: Jinja2Templates = Depends(get_templates)
):
    owner = crud.authenticate_owner(db, form_data.username, form_data.password)
    if not owner:
        return templates.TemplateResponse("login.html", {"request": request, "error": "Incorrect email or password", "lang": request.query_params.get("lang", "en")})
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": owner.email}, expires_delta=access_token_expires
    )
    response = RedirectResponse(url="/dashboard?lang=" + request.query_params.get("lang", "en"), status_code=status.HTTP_302_FOUND)
    response.set_cookie(key="access_token", value=access_token, httponly=True, expires=access_token_expires.total_seconds())
    return response

@app.get("/logout")
async def logout(response: Response, request: Request):
    lang_param = request.query_params.get("lang", "en")
    response = RedirectResponse(url=f"/login?lang={lang_param}", status_code=status.HTTP_302_FOUND)
    response.delete_cookie(key="access_token")
    return response

@app.get("/dashboard", response_class=HTMLResponse)
async def owner_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(get_current_owner),
    templates: Jinja2Templates = Depends(get_templates)
):
    bookings = db.query(models.Booking).filter(models.Booking.owner_id == current_owner.id).order_by(models.Booking.booking_time).all()
    
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
            "lang": request.query_params.get("lang", "en")
        }
    )

@app.post("/owner/me", response_class=HTMLResponse)
async def update_owner_profile(
    request: Request,
    name: str = Form(...),
    business_name: str = Form(...),
    phone: Optional[str] = Form(None),
    service_name: List[str] = Form([]),
    service_duration: List[int] = Form([]),
    service_price: List[float] = Form([]),
    service_description: List[str] = Form([]),
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(get_current_owner),
    templates: Jinja2Templates = Depends(get_templates)
):
    profile_update_data = schemas.OwnerProfileUpdate(
        name=name,
        business_name=business_name,
        phone=phone if phone else None
    )
    
    updated_owner = crud.update_owner_profile(db, current_owner, profile_update_data)

    new_services = []
    for i in range(len(service_name)):
        if service_name[i]:
            try:
                service = schemas.Service(
                    name=service_name[i],
                    duration=service_duration[i],
                    price=service_price[i],
                    description=service_description[i] if i < len(service_description) else None
                )
                new_services.append(service.dict())
            except Exception as e:
                bookings = db.query(models.Booking).filter(models.Booking.owner_id == current_owner.id).order_by(models.Booking.booking_time).all()
                return templates.TemplateResponse(
                    "dashboard.html",
                    {
                        "request": request,
                        "owner": current_owner,
                        "bookings": bookings,
                        "services": json.loads(current_owner.services_json), 
                        "availability": json.loads(current_owner.availability_json), 
                        "profile_error": f"Error updating services: {e}",
                        "lang": request.query_params.get("lang", "en")
                    }
                )
    updated_owner.services_json = json.dumps(new_services)

    new_availability = {}
    days_of_week = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    for day in days_of_week:
        start_times = request._form.getlist(f"availability_{day}_start")
        end_times = request._form.getlist(f"availability_{day}_end")
        slot_durations = request._form.getlist(f"availability_{day}_slot_duration")

        day_slots = []
        for i in range(len(start_times)):
            if start_times[i] and end_times[i] and slot_durations[i]:
                try:
                    slot = schemas.DayAvailability(
                        start_time=start_times[i],
                        end_time=end_times[i],
                        slot_duration=int(slot_durations[i])
                    )
                    day_slots.append(slot.dict())
                except Exception as e:
                    bookings = db.query(models.Booking).filter(models.Booking.owner_id == current_owner.id).order_by(models.Booking.booking_time).all()
                    return templates.TemplateResponse(
                        "dashboard.html",
                        {
                            "request": request,
                            "owner": current_owner,
                            "bookings": bookings,
                            "services": json.loads(updated_owner.services_json),
                            "availability": json.loads(current_owner.availability_json), 
                            "profile_error": f"Error updating availability for {day}: {e}",
                            "lang": request.query_params.get("lang", "en")
                        }
                    )
        if day_slots:
            new_availability[day] = day_slots
    
    updated_owner.availability_json = json.dumps(new_availability)
    
    db.add(updated_owner)
    db.commit()
    db.refresh(updated_owner)

    bookings = db.query(models.Booking).filter(models.Booking.owner_id == updated_owner.id).order_by(models.Booking.booking_time).all()
    
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "owner": updated_owner,
            "bookings": bookings,
            "services": json.loads(updated_owner.services_json),
            "availability": json.loads(updated_owner.availability_json),
            "profile_success": "Profile updated successfully!",
            "lang": request.query_params.get("lang", "en")
        }
    )


@app.get("/book/{owner_slug}", response_class=HTMLResponse, name="public_booking_page")
async def public_booking_page(
    owner_slug: str,
    request: Request,
    db: Session = Depends(get_db),
    templates: Jinja2Templates = Depends(get_templates)
):
    owner = crud.get_owner_by_slug(db, slug=owner_slug)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Owner not found")
    
    services = json.loads(owner.services_json) if owner.services_json else []
    
    return templates.TemplateResponse(
        "booking_page.html",
        {
            "request": request,
            "owner": owner,
            "services": services,
            "lang": request.query_params.get("lang", "en")
        }
    )

@app.post("/book/{owner_slug}", response_class=HTMLResponse)
async def submit_booking(
    owner_slug: str,
    request: Request,
    customer_name: str = Form(...),
    customer_email: str = Form(...),
    customer_phone: Optional[str] = Form(None),
    service_name: str = Form(...),
    booking_time: datetime = Form(...),
    db: Session = Depends(get_db),
    templates: Jinja2Templates = Depends(get_templates)
):
    owner = crud.get_owner_by_slug(db, slug=owner_slug)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Owner not found")

    services_list = json.loads(owner.services_json) if owner.services_json else []
    selected_service = next((s for s in services_list if s['name'] == service_name), None)

    if not selected_service:
        services_for_template = [schemas.Service(**s) for s in services_list]
        return templates.TemplateResponse(
            "booking_page.html",
            {
                "request": request,
                "owner": owner,
                "services": services_for_template,
                "error_message": "Invalid service selected.",
                "lang": request.query_params.get("lang", "en")
            },
            status_code=status.HTTP_400_BAD_REQUEST
        )

    try:
        booking_data = schemas.BookingCreate(
            customer_name=customer_name,
            customer_email=customer_email,
            customer_phone=customer_phone if customer_phone else None,
            service_name=service_name,
            booking_time=booking_time
        )
        db_booking = crud.create_booking(db=db, booking=booking_data, owner_id=owner.id)

        owner_subject = f"New Booking for {selected_service['name']} with {customer_name}"
        owner_html_content = f"""
            <p>Hello {owner.name},</p>
            <p>You have a new booking!</p>
            <ul>
                <li>Customer: {customer_name}</li>
                <li>Email: {customer_email}</li>
                <li>Phone: {customer_phone if customer_phone else 'N/A'}</li>
                <li>Service: {selected_service['name']}</li>
                <li>Time: {booking_time.strftime('%Y-%m-%d %H:%M')}</li>
            </ul>
            <p>Go to your dashboard: <a href="{request.url_for('owner_dashboard')}?lang={request.query_params.get('lang', 'en')}">Dashboard</a></p>
        """
        notifications.send_email_notification(owner.email, owner_subject, owner_html_content)
        if owner.phone:
            owner_whatsapp_message = (
                f"New BookSlot booking for {owner.business_name}!\n"
                f"Service: {selected_service['name']}\n"
                f"Time: {booking_time.strftime('%Y-%m-%d %H:%M')}\n"
                f"Customer: {customer_name} ({customer_phone if customer_phone else customer_email})"
            )
            notifications.send_whatsapp_notification(owner.phone, owner_whatsapp_message)

        customer_subject = f"Your Booking Confirmation with {owner.business_name}"
        customer_html_content = f"""
            <p>Hello {customer_name},</p>
            <p>Your booking with {owner.business_name} is confirmed!</p>
            <ul>
                <li>Service: {selected_service['name']}</li>
                <li>Time: {booking_time.strftime('%Y-%m-%d %H:%M')}</li>
                <li>Business: {owner.business_name}</li>
                <li>Contact: {owner.email} {f'/ {owner.phone}' if owner.phone else ''}</li>
            </ul>
            <p>We look forward to seeing you!</p>
        """
        notifications.send_email_notification(customer_email, customer_subject, customer_html_content)
        if customer_phone:
            customer_whatsapp_message = (
                f"Your BookSlot booking with {owner.business_name} is confirmed!\n"
                f"Service: {selected_service['name']}\n"
                f"Time: {booking_time.strftime('%Y-%m-%d %H:%M')}\n"
                f"Looking forward to seeing you!"
            )
            notifications.send_whatsapp_notification(customer_phone, customer_whatsapp_message)


        return templates.TemplateResponse(
            "booking_confirmation.html",
            {
                "request": request,
                "booking": db_booking,
                "owner": owner,
                "lang": request.query_params.get("lang", "en")
            }
        )
    except Exception as e:
        services_for_template = [schemas.Service(**s) for s in services_list]
        return templates.TemplateResponse(
            "booking_page.html",
            {
                "request": request,
                "owner": owner,
                "services": services_for_template,
                "error_message": f"An error occurred during booking: {e}",
                "lang": request.query_params.get("lang", "en")
            },
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
