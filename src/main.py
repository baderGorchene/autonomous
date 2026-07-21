import os
from fastapi import FastAPI, Request, Depends, Form, BackgroundTasks, HTTPException
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from . import i18n_config, models, schemas, database, notifications, crud
from .routes import booking, auth
from datetime import datetime
from typing import Optional

app = FastAPI()
app.include_router(booking.router, prefix="/book")
app.include_router(auth.router, prefix="/auth")

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
TEMPLATES_DIR = os.path.join(PROJECT_ROOT, "templates")

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
    return request.state.templates.TemplateResponse("dashboard.html", {
        "request": request,
        "bookings": bookings,
        "owner": current_owner,
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
    owner_update_schema = schemas.OwnerProfileUpdate(
        name=name,
        business_name=business_name,
        phone=phone
    )
    updated_owner = crud.update_owner_profile(db, current_owner, owner_update_schema)
    
    bookings = db.query(models.Booking).filter(models.Booking.owner_id == updated_owner.id).order_by(models.Booking.datetime.desc()).all()
    
    return request.state.templates.TemplateResponse("dashboard.html", {
        "request": request,
        "owner": updated_owner,
        "bookings": bookings,
        "lang": request.state.locale,
        "message": "Profile updated successfully!"
    })
