from fastapi import FastAPI, Depends, HTTPException, status, Request, Response, Form
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta, date, time
import json
import logging
from typing import List, Optional

from src.config import settings
from src.database import get_db, create_tables
from src import crud, models, schemas, security, notifications
from src.dependencies import get_current_owner
from src.i18n_config import get_jinja_templates, get_templates_env

# Initialize logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Create database tables on startup
@app.on_event("startup")
def on_startup():
    create_tables()
    logger.info("Database tables created/checked.")

# Middleware for i18n
@app.middleware("http")
async def add_i18n_middleware(request: Request, call_next):
    lang = request.cookies.get("lang", "en")
    if "lang" in request.query_params:
        lang = request.query_params["lang"]
    request.state.lang = lang
    response = await call_next(request)
    if "lang" in request.query_params:
        response.set_cookie(key="lang", value=lang, httponly=True, expires=timedelta(days=30))
    return response

# --- API Endpoints ---

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
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": owner.email}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/health")
async def health_check():
    return {"status": "ok", "message": "BookSlot service is running"}

# --- Web Endpoints (HTML Pages) ---

@app.get("/signup", response_class=Response)
async def get_signup_page(request: Request, templates=Depends(get_templates_env)):
    return templates.TemplateResponse("signup.html", {"request": request})

@app.post("/signup", response_class=Response)
async def post_signup_page(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    business_name: str = Form(...),
    slug: str = Form(...),
    phone: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    templates=Depends(get_templates_env)
):
    owner = crud.get_owner_by_email(db, email=email)
    if owner:
        return templates.TemplateResponse("signup.html", {"request": request, "error": "Email already registered."},
                                          status_code=status.HTTP_400_BAD_REQUEST)
    owner = crud.get_owner_by_slug(db, slug=slug)
    if owner:
        return templates.TemplateResponse("signup.html", {"request": request, "error": "Business URL already taken."},
                                          status_code=status.HTTP_400_BAD_REQUEST)

    try:
        owner_in = schemas.OwnerCreate(name=name, email=email, password=password, business_name=business_name, slug=slug, phone=phone)
        db_owner = crud.create_owner(db=db, owner=owner_in)
        return templates.TemplateResponse("login.html", {"request": request, "message": "Account created successfully! Please log in."},
                                          status_code=status.HTTP_201_CREATED)
    except Exception as e:
        logger.error(f"Signup error: {e}")
        return templates.TemplateResponse("signup.html", {"request": request, "error": "An error occurred during signup."},
                                          status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

@app.get("/login", response_class=Response)
async def get_login_page(request: Request, templates=Depends(get_templates_env)):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login", response_class=Response)
async def post_login_page(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
    templates=Depends(get_templates_env)
):
    owner = crud.authenticate_owner(db, email, password)
    if not owner:
        return templates.TemplateResponse("login.html", {"request": request, "error": "Incorrect email or password"},
                                          status_code=status.HTTP_401_UNAUTHORIZED)

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": owner.email}, expires_delta=access_token_expires
    )
    response = templates.TemplateResponse("dashboard.html", {"request": request, "owner": owner}, status_code=status.HTTP_303_SEE_OTHER)
    response.headers["Location"] = "/dashboard" # Redirect after successful login
    response.set_cookie(key="access_token", value=access_token, httponly=True, expires=access_token_expires)
    response.set_cookie(key="token_type", value="bearer", httponly=True, expires=access_token_expires)
    return response

@app.get("/logout")
async def logout(request: Request, templates=Depends(get_templates_env)):
    response = templates.TemplateResponse("login.html", {"request": request, "message": "You have been logged out."},
                                      status_code=status.HTTP_200_OK)
    response.delete_cookie("access_token")
    response.delete_cookie("token_type")
    return response

@app.get("/dashboard", response_class=Response)
async def get_dashboard(request: Request, current_owner: models.Owner = Depends(get_current_owner), db: Session = Depends(get_db), templates=Depends(get_templates_env)):
    bookings = crud.get_owner_bookings(db, current_owner.id)
    # Convert services_json and availability_json to Python objects for template
    current_owner.services = json.loads(current_owner.services_json) if current_owner.services_json else []
    current_owner.availability = json.loads(current_owner.availability_json) if current_owner.availability_json else {}
    return templates.TemplateResponse("dashboard.html", {"request": request, "owner": current_owner, "bookings": bookings})

@app.post("/dashboard/profile", response_class=Response)
async def update_profile(
    request: Request,
    name: str = Form(...),
    business_name: str = Form(...),
    phone: Optional[str] = Form(None),
    services_json_str: str = Form("[]", alias="services"), # Expect JSON string from form
    availability_json_str: str = Form("{}", alias="availability"), # Expect JSON string from form
    current_owner: models.Owner = Depends(get_current_owner),
    db: Session = Depends(get_db),
    templates=Depends(get_templates_env)
):
    try:
        # Validate JSON strings
        services_data = json.loads(services_json_str)
        availability_data = json.loads(availability_json_str)

        # Optional: Further validate services_data and availability_data against schemas
        # For simplicity, we'll just store the validated JSON strings for now.
        # In a real app, you'd convert to List[ServiceSchema] and List[AvailabilitySchema]

        owner_update = schemas.OwnerProfileUpdate(
            name=name,
            business_name=business_name,
            phone=phone,
            # services and availability are handled directly on the model as JSON strings
        )
        updated_owner = crud.update_owner_profile(db, current_owner, owner_update)
        updated_owner.services_json = services_json_str
        updated_owner.availability_json = availability_json_str
        db.add(updated_owner)
        db.commit()
        db.refresh(updated_owner)

        # Reload data for template
        bookings = crud.get_owner_bookings(db, updated_owner.id)
        updated_owner.services = json.loads(updated_owner.services_json)
        updated_owner.availability = json.loads(updated_owner.availability_json)

        return templates.TemplateResponse("dashboard.html", {"request": request, "owner": updated_owner, "bookings": bookings, "message": "Profile updated successfully!"})
    except json.JSONDecodeError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON format for services or availability.")
    except Exception as e:
        logger.error(f"Error updating profile: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An error occurred while updating the profile.")

@app.get("/{owner_slug}", response_class=Response)
async def get_booking_page(request: Request, owner_slug: str, db: Session = Depends(get_db), templates=Depends(get_templates_env)):
    owner = crud.get_owner_by_slug(db, slug=owner_slug)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Owner not found.")

    services = json.loads(owner.services_json) if owner.services_json else []
    availability = json.loads(owner.availability_json) if owner.availability_json else {}

    return templates.TemplateResponse("booking_page.html", {"request": request, "owner": owner, "services": services, "availability": availability})

@app.post("/{owner_slug}", response_class=Response)
async def post_booking_page(
    request: Request,
    owner_slug: str,
    customer_name: str = Form(...),
    customer_email: str = Form(...),
    customer_phone: Optional[str] = Form(None),
    booking_date_str: str = Form(..., alias="booking_date"),
    booking_time_str: str = Form(..., alias="booking_time"),
    service_name: str = Form(...),
    db: Session = Depends(get_db),
    templates=Depends(get_templates_env)
):
    owner = crud.get_owner_by_slug(db, slug=owner_slug)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Owner not found.")

    try:
        booking_date_obj = date.fromisoformat(booking_date_str)
        booking_time_obj = time.fromisoformat(booking_time_str)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid date or time format.")

    # Basic availability check (more robust logic needed for real app)
    # For MVP, just check if the service exists and a slot *could* exist.
    services = json.loads(owner.services_json) if owner.services_json else []
    selected_service = next((s for s in services if s['name'] == service_name), None)
    if not selected_service:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Selected service is not offered.")

    # For a full booking system, you'd check actual slot availability, overlaps, etc.
    # This MVP assumes basic trust or that owner manages availability well.

    booking_in = schemas.BookingCreate(
        customer_name=customer_name,
        customer_email=customer_email,
        customer_phone=customer_phone,
        booking_date=booking_date_obj,
        booking_time=booking_time_obj,
        service_name=service_name,
    )

    try:
        db_booking = crud.create_booking(db=db, booking=booking_in, owner_id=owner.id)

        booking_details = booking_in.dict()
        booking_details['booking_date'] = booking_details['booking_date'].isoformat()
        booking_details['booking_time'] = booking_details['booking_time'].isoformat()

        # Send notifications
        notifications.send_booking_confirmation_emails(
            owner_email=owner.email,
            customer_email=customer_email,
            booking_details=booking_details,
            owner_name=owner.name,
            business_name=owner.business_name
        )
        notifications.send_booking_confirmation_whatsapp(
            owner_phone=owner.phone,
            customer_phone=customer_phone,
            booking_details=booking_details,
            business_name=owner.business_name
        )

        return templates.TemplateResponse("booking_confirmation.html", {"request": request, "booking": db_booking, "owner": owner}, status_code=status.HTTP_201_CREATED)
    except Exception as e:
        logger.error(f"Error creating booking: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An error occurred during booking.")

# Generic error handler for HTTPException
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException, templates=Depends(get_templates_env)):
    # Attempt to render a generic error page or return JSON for API calls
    if request.headers.get("accept") and "text/html" in request.headers.get("accept"):
        return templates.TemplateResponse(
            "error.html", {"request": request, "detail": exc.detail, "status_code": exc.status_code},
            status_code=exc.status_code
        )
    return {"detail": exc.detail}, exc.status_code
