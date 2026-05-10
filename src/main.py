from fastapi import FastAPI, Request, Depends, Form, BackgroundTasks, HTTPException
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from . import i18n_config, models, schemas, database, notifications
from .routes import booking, auth
from datetime import datetime

app = FastAPI()
app.include_router(booking.router, prefix="/book")
app.include_router(auth.router, prefix="/auth")

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
    request.state.templates = Jinja2Templates(directory="templates")
    request.state.templates.env = i18n_config.get_jinja_env(locale=locale)
    response = await call_next(request)
    return response

@app.get("/dashboard/{owner_id}")
def get_dashboard(owner_id: int, request: Request, db: Session = Depends(get_db)):
    bookings = db.query(models.Booking).filter(models.Booking.owner_id == owner_id).order_by(models.Booking.datetime.desc()).all()
    return request.state.templates.TemplateResponse("dashboard.html", {"request": request, "bookings": bookings, "lang": request.state.locale})