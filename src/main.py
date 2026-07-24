import os
from fastapi import FastAPI, Request, Depends, Form, BackgroundTasks, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from pydantic import ValidationError
from . import i18n_config, models, schemas, database, notifications, crud, security
from .routes import booking, auth
from datetime import datetime
from typing import Optional
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI()
app.include_router(booking.router, prefix="/book")
app.include_router(auth.router, prefix="/auth")

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
TEMPLATES_DIR = os.path.join(PROJECT_ROOT, "templates")
STATIC_DIR = os.path.join(PROJECT_ROOT, "static")

# Mount static files
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.middleware("http")
async def add_locale_middleware(request: Request, call_next):
    locale = request.query_params.get("lang", "en")
    request.state.locale = locale
    request.state.templates = Jinja2Templates(directory=TEMPLATES_DIR)
    request.state.templates.env = i18n_config.get_jinja_env(locale=locale, templates_dir=TEMPLATES_DIR, project_root=PROJECT_ROOT)
    response = await call_next(request)
    return response

@app.get("/dashboard")
def get_dashboard(request: Request, current_owner: models.Owner = Depends(auth.get_current_owner), db: Session = Depends(get_db)):
    bookings = db.query(models.Booking).filter(models.Booking.owner_id == current_owner.id).order_by(models.Booking.datetime.desc()).all()
    
    owner_services = [schemas.ServiceSchema(**s) for s in current_owner.services_json] if current_owner.services_json else []
    owner_availability = current_owner.availability_json if current_owner.availability_json else {}

    return request.state.templates.TemplateResponse("dashboard.html", {
        "request": request,
        "bookings": bookings,
        "owner": current_owner,
        "services": owner_services,
        "availability": owner_availability,
        "lang": request.state.locale
    })

@app.post("/dashboard/profile")
async def update_owner_profile_route(
    request: Request,
    name: str = Form(...),
    business_name: str = Form(...),
    phone: Optional[str] = Form(None),
    current_owner: models.Owner = Depends(auth.get_current_owner),
    db: Session = Depends(get_db)
):
    message = None
    error_message = None
    updated_owner = current_owner

    try:
        owner_update_schema = schemas.OwnerProfileUpdate(
            name=name,
            business_name=business_name,
            phone=phone
        )
        updated_owner = crud.update_owner_profile(db, current_owner, owner_update_schema)
        message = request.state.templates.env.gettext("Profile updated successfully!")
    except ValidationError as e:
        logger.error(f"Validation error during owner profile update: {e.errors()}")
        error_message = request.state.templates.env.gettext(f"Invalid input for profile update: {e.errors()}")
    except SQLAlchemyError as e:
        logger.exception(f"Database error during owner profile update: {e}")
        db.rollback()
        error_message = request.state.templates.env.gettext("A database error occurred while updating your profile. Please try again.")
    except Exception as e:
        logger.exception(f"Unexpected error during owner profile update: {e}")
        error_message = request.state.templates.env.gettext("An unexpected error occurred. Please try again.")
    
    bookings = db.query(models.Booking).filter(models.Booking.owner_id == updated_owner.id).order_by(models.Booking.datetime.desc()).all()
    
    owner_services = [schemas.ServiceSchema(**s) for s in updated_owner.services_json] if updated_owner.services_json else []
    owner_availability = updated_owner.availability_json if updated_owner.availability_json else {}

    return request.state.templates.TemplateResponse("dashboard.html", {
        "request": request,
        "owner": updated_owner,
        "bookings": bookings,
        "services": owner_services,
        "availability": owner_availability,
        "lang": request.state.locale,
        "message": message,
        "error_message": error_message
    })

@app.get("/health")
async def health_check():
    return {"status": "ok", "message": "BookSlot service is running."}