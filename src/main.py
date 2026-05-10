from fastapi import FastAPI, Request, Depends, Form, BackgroundTasks, HTTPException
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from . import i18n_config, models, schemas, database, notifications
from datetime import datetime

app = FastAPI()

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

@app.post("/book/{owner_slug}")
async def create_booking(
    owner_slug: str,
    background_tasks: BackgroundTasks,
    customer_name: str = Form(...),
    customer_email: str = Form(...),
    customer_phone: str = Form(...),
    service_name: str = Form(...),
    booking_datetime: datetime = Form(...),
    db: Session = Depends(get_db)
):
    owner = db.query(models.Owner).filter(models.Owner.slug == owner_slug).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")
    
    new_booking = models.Booking(
        owner_id=owner.id,
        customer_name=customer_name,
        customer_email=customer_email,
        customer_phone=customer_phone,
        service=service_name,
        datetime=booking_datetime
    )
    db.add(new_booking)
    db.commit()
    db.refresh(new_booking)
    
    background_tasks.add_task(
        notifications.send_booking_notification,
        owner.email, 
        owner.phone if hasattr(owner, 'phone') else "",
        {"customer": customer_name, "time": booking_datetime.isoformat()}
    )
    return {"status": "success", "booking_id": new_booking.id}