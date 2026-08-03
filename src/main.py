from fastapi import FastAPI, Depends, HTTPException, status, Request, Form, Response
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import timedelta, date, datetime
import json
import os
import logging
from starlette.middleware.sessions import SessionMiddleware

from . import crud, models, schemas, security, notifications
from .database import SessionLocal, engine, create_tables, get_db
from .dependencies import get_current_owner
from .config import settings
from .i18n_config import get_jinja_templates, TEMPLATES_DIR, LOCALES_DIR

# Ensure tables are created on startup
models.Base.metadata.create_all(bind=engine)

logger = logging.getLogger(__name__)

app = FastAPI()

# Add Session Middleware for language preference
# !!! IMPORTANT: Change the secret key in production and keep it secret !!!
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

# Middleware to set language and load templates
@app.middleware("http")
async def add_i18n_middleware(request: Request, call_next):
    lang = request.session.get('lang', 'en')
    
    # Check if language is provided in query params and update session
    query_lang = request.query_params.get('lang')
    if query_lang and query_lang in ['en', 'ar', 'fr']:
        lang = query_lang
        request.session['lang'] = lang
        
        # Redirect to clean the URL if lang param was present, to avoid persistence in URL
        # This ensures subsequent requests don't keep the 'lang' query param
        if request.method == 'GET':
            redirect_url = str(request.url).split('?')[0]
            if request.query_params:
                # Reconstruct query params without 'lang'
                filtered_params = {k: v for k, v in request.query_params.items() if k != 'lang'}
                if filtered_params:
                    redirect_url += '?' + '&'.join(f'{k}={v}' for k,v in filtered_params.items())
            response = RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)
            response.set_cookie(key='lang', value=lang) # Also set cookie for client-side use if needed
            return response

    # Fallback to cookie if session not set (e.g., first visit, or no session middleware)
    if not request.session.get('lang') and request.cookies.get('lang'):
        lang = request.cookies.get('lang')
        request.session['lang'] = lang

    request.state.lang = lang
    request.state.templates = get_jinja_templates(lang)
    
    response = await call_next(request)
    response.set_cookie(key='lang', value=lang) # Keep cookie updated
    return response

# Dependency to get Jinja2Templates instance with current locale
def get_templates_env(request: Request):
    return request.state.templates

# Root endpoint
@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request, templates: Jinja2Templates = Depends(get_templates_env)):
    return templates.TemplateResponse("index.html", {"request": request, "current_lang": request.state.lang})

@app.get("/health")
async def health_check():
    return {"status": "ok"}

# Owner signup
@app.get("/signup", response_class=HTMLResponse)
async def signup_form(request: Request, templates: Jinja2Templates = Depends(get_templates_env), msg: Optional[str] = None):
    return templates.TemplateResponse("signup.html", {"request": request, "msg": msg, "current_lang": request.state.lang})

@app.post("/signup", response_class=HTMLResponse)
async def signup_owner(
    request: Request,
    db: Session = Depends(get_db),
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    business_name: str = Form(...),
    slug: str = Form(...),
    phone: Optional[str] = Form(None),
    templates: Jinja2Templates = Depends(get_templates_env)
):
    db_owner = crud.get_owner_by_email(db, email=email)
    if db_owner:
        return templates.TemplateResponse("signup.html", {"request": request, "msg": _("Email already registered"), "current_lang": request.state.lang}, status_code=status.HTTP_400_BAD_REQUEST)
    
    db_owner = crud.get_owner_by_slug(db, slug=slug)
    if db_owner:
        return templates.TemplateResponse("signup.html", {"request": request, "msg": _("Business link already taken"), "current_lang": request.state.lang}, status_code=status.HTTP_400_BAD_REQUEST)

    owner = schemas.OwnerCreate(name=name, email=email, password=password, business_name=business_name, slug=slug, phone=phone)
    crud.create_owner(db=db, owner=owner)
    return RedirectResponse(url="/login?msg=Signup successful, please log in", status_code=status.HTTP_302_FOUND)

# Owner login
@app.get("/login", response_class=HTMLResponse)
async def login_form(request: Request, templates: Jinja2Templates = Depends(get_templates_env), msg: Optional[str] = None):
    return templates.TemplateResponse("login.html", {"request": request, "msg": msg, "current_lang": request.state.lang})

@app.post("/login", response_class=HTMLResponse)
async def login_for_access_token(
    request: Request,
    db: Session = Depends(get_db),
    form_data: OAuth2PasswordRequestForm = Depends(),
    templates: Jinja2Templates = Depends(get_templates_env)
):
    owner = crud.authenticate_owner(db, form_data.username, form_data.password)
    if not owner:
        return templates.TemplateResponse("login.html", {"request": request, "msg": _("Incorrect email or password"), "current_lang": request.state.lang}, status_code=status.HTTP_401_UNAUTHORIZED)
    
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": owner.email},
        expires_delta=access_token_expires
    )
    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    response.set_cookie(key="access_token", value=f"Bearer {access_token}", httponly=True)
    return response

# Owner dashboard
@app.get("/dashboard", response_class=HTMLResponse)
async def owner_dashboard(
    request: Request,
    templates: Jinja2Templates = Depends(get_templates_env),
    current_owner: schemas.Owner = Depends(get_current_owner),
    db: Session = Depends(get_db)
):
    bookings = crud.get_owner_bookings(db, owner_id=current_owner.id)
    return templates.TemplateResponse("dashboard.html", {"request": request, "owner": current_owner, "bookings": bookings, "current_lang": request.state.lang})

@app.get("/dashboard/profile", response_class=HTMLResponse)
async def owner_profile_page(
    request: Request,
    templates: Jinja2Templates = Depends(get_templates_env),
    current_owner: schemas.Owner = Depends(get_current_owner),
    msg: Optional[str] = None
):
    return templates.TemplateResponse("profile.html", {"request": request, "owner": current_owner, "msg": msg, "current_lang": request.state.lang})

@app.post("/dashboard/profile", response_class=HTMLResponse)
async def update_owner_profile_post(
    request: Request,
    db: Session = Depends(get_db),
    current_owner: schemas.Owner = Depends(get_current_owner),
    name: str = Form(...),
    business_name: str = Form(...),
    phone: Optional[str] = Form(None),
    templates: Jinja2Templates = Depends(get_templates_env)
):
    owner_update = schemas.OwnerProfileUpdate(name=name, business_name=business_name, phone=phone)
    try:
        updated_owner = crud.update_owner_profile(db, current_owner, owner_update)
        return templates.TemplateResponse("profile.html", {"request": request, "owner": updated_owner, "msg": _("Profile updated successfully!"), "current_lang": request.state.lang})
    except Exception as e:
        logger.error(f"Error updating owner profile: {e}")
        return templates.TemplateResponse("profile.html", {"request": request, "owner": current_owner, "msg": _("Error updating profile."), "current_lang": request.state.lang}, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

# Logout
@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/login?msg=You have been logged out.", status_code=status.HTTP_302_FOUND)
    response.delete_cookie("access_token")
    return response

# Public booking page
@app.get("/{owner_slug}", response_class=HTMLResponse)
async def booking_page(
    request: Request,
    owner_slug: str,
    templates: Jinja2Templates = Depends(get_templates_env),
    db: Session = Depends(get_db),
    msg: Optional[str] = None
):
    owner = crud.get_owner_by_slug(db, slug=owner_slug)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Owner not found"))
    
    # Parse services and availability
    services = json.loads(owner.services_json) if owner.services_json else []
    availability = json.loads(owner.availability_json) if owner.availability_json else {}

    # Example of generating available slots (simplified for MVP)
    # In a real app, this would be more sophisticated, checking existing bookings.
    available_slots = []
    today = date.today()
    for i in range(7): # Next 7 days
        current_date = today + timedelta(days=i)
        day_of_week = current_date.weekday() # Monday is 0, Sunday is 6
        
        daily_slots_config = []
        if str(day_of_week) in availability:
            daily_slots_config = availability[str(day_of_week)]

        day_slots = []
        for slot_config in daily_slots_config:
            start_time_str = slot_config['start_time']
            end_time_str = slot_config['end_time']
            # Assuming 1-hour slots for simplicity, adjust based on service duration
            current_slot_start = datetime.strptime(start_time_str, "%H:%M").time()
            slot_end_limit = datetime.strptime(end_time_str, "%H:%M").time()
            
            while current_slot_start < slot_end_limit:
                slot_end = (datetime.combine(current_date, current_slot_start) + timedelta(minutes=60)).time()
                if slot_end > slot_end_limit: # Ensure slot doesn't exceed daily limit
                    break
                day_slots.append(f"{current_slot_start.strftime('%H:%M')}-{slot_end.strftime('%H:%M')}")
                current_slot_start = slot_end
        
        if day_slots:
            available_slots.append({
                "date": current_date.isoformat(),
                "day_name": current_date.strftime("%A"),
                "slots": day_slots
            })

    return templates.TemplateResponse(
        "booking_page.html", 
        {"request": request, "owner": owner, "services": services, "available_slots": available_slots, "msg": msg, "current_lang": request.state.lang}
    )

@app.post("/{owner_slug}/book", response_class=HTMLResponse)
async def submit_booking(
    request: Request,
    owner_slug: str,
    templates: Jinja2Templates = Depends(get_templates_env),
    db: Session = Depends(get_db),
    customer_name: str = Form(...),
    customer_email: str = Form(...),
    customer_phone: Optional[str] = Form(None),
    service_name: str = Form(...),
    booking_date: str = Form(...), # ISO format date string
    booking_time: str = Form(...)
):
    owner = crud.get_owner_by_slug(db, slug=owner_slug)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Owner not found"))
    
    try:
        parsed_booking_date = date.fromisoformat(booking_date)
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
        # Owner notification
        owner_subject = _("New Booking Received!")
        owner_html_content = templates.get_template("email/owner_booking_notification.html").render(
            booking=db_booking, owner=owner, _=request.state.templates.env.gettext
        )
        notifications.send_email_notification(owner.email, owner_subject, owner_html_content)
        if owner.phone:
            owner_whatsapp_msg = _(f"New booking for {service_name} on {booking_date} at {booking_time} by {customer_name}.")
            notifications.send_whatsapp_notification(owner.phone, owner_whatsapp_msg)

        # Customer confirmation
        customer_subject = _("Your Booking is Confirmed!")
        customer_html_content = templates.get_template("email/customer_booking_confirmation.html").render(
            booking=db_booking, owner=owner, _=request.state.templates.env.gettext
        )
        notifications.send_email_notification(customer_email, customer_subject, customer_html_content)

        return templates.TemplateResponse("booking_confirmation.html", {"request": request, "owner": owner, "booking": db_booking, "current_lang": request.state.lang})
    except Exception as e:
        logger.error(f"Error processing booking for {owner_slug}: {e}")
        # Redirect back to booking page with an error message
        return RedirectResponse(url=f"/{owner_slug}?msg={_('There was an error processing your booking. Please try again.')}", status_code=status.HTTP_302_FOUND)

