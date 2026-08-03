from fastapi import FastAPI, Request, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from src.database import create_tables, get_db
from src.config import settings
from src.i18n_config import get_templates_env
from src import schemas, crud, security
from fastapi.security import OAuth2PasswordRequestForm
from datetime import timedelta
import json

app = FastAPI()

# Middleware to set language
@app.middleware("http")
async def add_language_middleware(request: Request, call_next):
    lang = request.query_params.get("lang", "en")
    if lang not in ["en", "ar", "fr"]:
        lang = "en" # Default to English if invalid
    request.state.lang = lang
    response = await call_next(request)
    return response

# Dependency to get templates based on current request's language
def get_templates(request: Request = Depends()):
    return get_templates_env(request)

@app.on_event("startup")
def on_startup():
    create_tables()

@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.get("/", response_class=HTMLResponse)
async def root(request: Request, templates: Jinja2Templates = Depends(get_templates)):
    return templates.TemplateResponse("root.html", {"request": request, "current_lang": request.state.lang})

# --- Authentication Routes ---
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

# --- Owner Routes ---
@app.post("/owners/", response_model=schemas.Owner)
async def create_owner(owner: schemas.OwnerCreate, db: Session = Depends(get_db)):
    db_owner = crud.get_owner_by_email(db, email=owner.email)
    if db_owner:
        raise HTTPException(status_code=400, detail="Email already registered")
    db_owner = crud.get_owner_by_slug(db, slug=owner.slug)
    if db_owner:
        raise HTTPException(status_code=400, detail="Business URL slug already taken")
    return crud.create_owner(db=db, owner=owner)

# Placeholder for dashboard - will be a template response in a real app
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, templates: Jinja2Templates = Depends(get_templates)): # Add templates dependency
    return templates.TemplateResponse("dashboard.html", {"request": request, "current_lang": request.state.lang, "owner": None, "bookings": []}) # Dummy data

# Placeholder for owner profile update
@app.post("/profile", response_model=schemas.Owner)
async def update_profile(owner_update: schemas.OwnerProfileUpdate, db: Session = Depends(get_db), current_owner: schemas.Owner = Depends(security.get_current_owner)):
    updated_owner = crud.update_owner_profile(db, current_owner, owner_update)
    return updated_owner

# --- Public Booking Page Routes ---
@app.get("/{owner_slug}", response_class=HTMLResponse)
async def get_booking_page(owner_slug: str, request: Request, templates: Jinja2Templates = Depends(get_templates), db: Session = Depends(get_db)):
    owner = crud.get_owner_by_slug(db, slug=owner_slug)
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")
    
    # Deserialize services and availability
    services = json.loads(owner.services_json) if owner.services_json else []
    availability = json.loads(owner.availability_json) if owner.availability_json else {}

    return templates.TemplateResponse(
        "booking_page.html",
        {
            "request": request,
            "owner": owner,
            "services": services,
            "availability": availability,
            "current_lang": request.state.lang
        }
    )

@app.post("/{owner_slug}/book", response_class=HTMLResponse)
async def create_booking_for_owner(
    owner_slug: str,
    booking: schemas.BookingCreate,
    request: Request,
    templates: Jinja2Templates = Depends(get_templates),
    db: Session = Depends(get_db)
):
    owner = crud.get_owner_by_slug(db, slug=owner_slug)
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")

    # Basic validation (more robust validation would be needed)
    if not booking.customer_name or not booking.customer_email or not booking.service_name or not booking.booking_date or not booking.booking_time:
        raise HTTPException(status_code=400, detail="Missing required booking information")

    # Create the booking
    db_booking = crud.create_booking(db=db, booking=booking, owner_id=owner.id)

    # In a real application, you'd send notifications here
    # notifications.send_email_confirmation(owner.email, booking.customer_email, db_booking)
    # notifications.send_whatsapp_notification(owner.phone, db_booking)
    
    return templates.TemplateResponse(
        "booking_confirmation.html",
        {
            "request": request,
            "owner": owner,
            "booking": db_booking,
            "current_lang": request.state.lang
        }
    )
