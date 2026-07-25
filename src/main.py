from fastapi import FastAPI, Depends, HTTPException, status, Request, Form, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta, datetime
from typing import List, Optional
from jinja2 import Environment, FileSystemLoader
import os
import gettext

from src import crud, models, schemas, security, notifications
from src.database import SessionLocal, engine
from src.config import settings
from src.i18n_config import get_jinja_env

models.Base.metadata.create_all(bind=engine)

app = FastAPI()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "../templates")
LOCALES_DIR = os.path.join(os.path.dirname(__file__), "../locales")

def get_template_env(request: Request):
    lang = request.cookies.get("lang", "en")
    return get_jinja_env(locale=lang, templates_dir=TEMPLATES_DIR, project_root=os.path.dirname(os.path.dirname(__file__)))


async def get_current_owner(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = security.decode_access_token(token)
    if payload is None:
        raise credentials_exception
    email: str = payload.get("sub")
    if email is None:
        raise credentials_exception
    owner = crud.get_owner_by_email(db, email=email)
    if owner is None:
        raise credentials_exception
    return owner

async def get_current_active_owner(current_owner: schemas.Owner = Depends(get_current_owner)):
    return current_owner

@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.post("/token", response_model=schemas.Token)
async def login_for_access_token(response: Response, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
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
    response.set_cookie(key="access_token", value=access_token, httponly=True, samesite="Lax")
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    env = get_template_env(request)
    template = env.get_template("login.html")
    return template.render(request=request)

@app.post("/login", response_class=HTMLResponse)
async def handle_login(request: Request, response: Response, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    try:
        token_response = await login_for_access_token(response, OAuth2PasswordRequestForm(username=email, password=password), db)
        if token_response:
            return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    except HTTPException as e:
        env = get_template_env(request)
        template = env.get_template("login.html")
        return template.render(request=request, error=e.detail)
    return RedirectResponse(url="/login?error=Invalid credentials", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request):
    env = get_template_env(request)
    template = env.get_template("signup.html")
    return template.render(request=request)

@app.post("/signup", response_class=HTMLResponse)
async def handle_signup(request: Request,
                        name: str = Form(...),
                        email: str = Form(...),
                        password: str = Form(...),
                        business_name: str = Form(...),
                        slug: str = Form(...),
                        db: Session = Depends(get_db)):
    env = get_template_env(request)
    template = env.get_template("signup.html")
    if crud.get_owner_by_email(db, email=email):
        return template.render(request=request, error="Email already registered")
    if crud.get_owner_by_slug(db, slug=slug):
        return template.render(request=request, error="Slug already taken")

    try:
        owner = schemas.OwnerCreate(name=name, email=email, password=password, business_name=business_name, slug=slug)
        crud.create_owner(db=db, owner=owner)
        response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
        return response
    except Exception as e:
        return template.render(request=request, error=f"An error occurred: {e}")

@app.get("/dashboard", response_class=HTMLResponse)
async def owner_dashboard(request: Request, db: Session = Depends(get_db), current_owner: models.Owner = Depends(get_current_active_owner)):
    env = get_template_env(request)
    template = env.get_template("dashboard.html")
    
    upcoming_bookings = db.query(models.Booking).filter(
        models.Booking.owner_id == current_owner.id,
        models.Booking.booking_time >= datetime.utcnow()
    ).order_by(models.Booking.booking_time).all()

    return template.render(request=request, owner=current_owner, bookings=upcoming_bookings)

@app.post("/dashboard/profile", response_class=HTMLResponse)
async def update_owner_profile(request: Request,
                               name: str = Form(...),
                               business_name: str = Form(...),
                               phone: Optional[str] = Form(None),
                               db: Session = Depends(get_db),
                               current_owner: models.Owner = Depends(get_current_active_owner)):
    env = get_template_env(request)
    template = env.get_template("dashboard.html")
    try:
        owner_update = schemas.OwnerProfileUpdate(name=name, business_name=business_name, phone=phone)
        updated_owner = crud.update_owner_profile(db, current_owner, owner_update)
        
        upcoming_bookings = db.query(models.Booking).filter(
            models.Booking.owner_id == updated_owner.id,
            models.Booking.booking_time >= datetime.utcnow()
        ).order_by(models.Booking.booking_time).all()

        return template.render(request=request, owner=updated_owner, bookings=upcoming_bookings, success_message="Profile updated successfully!")
    except Exception as e:
        upcoming_bookings = db.query(models.Booking).filter(
            models.Booking.owner_id == current_owner.id,
            models.Booking.booking_time >= datetime.utcnow()
        ).order_by(models.Booking.booking_time).all()
        return template.render(request=request, owner=current_owner, bookings=upcoming_bookings, error_message=f"Error updating profile: {e}")

@app.get("/{owner_slug}", response_class=HTMLResponse)
async def public_booking_page(request: Request, owner_slug: str, db: Session = Depends(get_db)):
    env = get_template_env(request)
    template = env.get_template("booking_page.html")
    owner = crud.get_owner_by_slug(db, owner_slug)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Owner not found")

    services = owner.services_json if owner.services_json else [
        schemas.Service(name="Consultation", duration_minutes=30, price=50.0).dict(),
        schemas.Service(name="Follow-up", duration_minutes=60, price=100.0).dict(),
    ]
    availability = owner.availability_json if owner.availability_json else {
        "Monday": [{"start_time": "09:00", "end_time": "17:00"}],
        "Tuesday": [{"start_time": "09:00", "end_time": "17:00"}],
        "Wednesday": [{"start_time": "09:00", "end_time": "17:00"}],
        "Thursday": [{"start_time": "09:00", "end_time": "17:00"}],
        "Friday": [{"start_time": "09:00", "end_time": "17:00"}],
    }

    services_obj = [schemas.Service(**s) for s in services]
    
    return template.render(request=request, owner=owner, services=services_obj, availability=availability)

@app.post("/{owner_slug}/book", response_class=HTMLResponse)
async def submit_booking(request: Request,
                         owner_slug: str,
                         customer_name: str = Form(...),
                         customer_email: str = Form(...),
                         customer_phone: Optional[str] = Form(None),
                         service_name: str = Form(...),
                         booking_date: str = Form(...),
                         booking_time: str = Form(...),
                         db: Session = Depends(get_db)):
    env = get_template_env(request)
    owner = crud.get_owner_by_slug(db, owner_slug)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Owner not found")

    full_booking_datetime_str = f"{booking_date} {booking_time}"
    try:
        booking_dt = datetime.strptime(full_booking_datetime_str, "%Y-%m-%d %H:%M")
    except ValueError:
        return env.get_template("booking_page.html").render(
            request=request, owner=owner, services=[schemas.Service(**s) for s in owner.services_json], 
            availability=owner.availability_json, error_message="Invalid date or time format.")

    if booking_dt <= datetime.utcnow():
        return env.get_template("booking_page.html").render(
            request=request, owner=owner, services=[schemas.Service(**s) for s in owner.services_json], 
            availability=owner.availability_json, error_message="Booking must be in the future.")

    selected_service = next((s for s in owner.services_json if s.get("name") == service_name), None)
    if not selected_service:
        return env.get_template("booking_page.html").render(
            request=request, owner=owner, services=[schemas.Service(**s) for s in owner.services_json], 
            availability=owner.availability_json, error_message="Selected service not found.")
    
    duration_minutes = selected_service.get("duration_minutes", 30)

    existing_bookings = db.query(models.Booking).filter(
        models.Booking.owner_id == owner.id,
        models.Booking.booking_time == booking_dt
    ).first()

    if existing_bookings:
         return env.get_template("booking_page.html").render(
            request=request, owner=owner, services=[schemas.Service(**s) for s in owner.services_json], 
            availability=owner.availability_json, error_message="This time slot is already booked.")


    try:
        booking_data = schemas.BookingCreate(
            customer_name=customer_name,
            customer_email=customer_email,
            customer_phone=customer_phone,
            service_name=service_name,
            booking_time=booking_dt,
            duration_minutes=duration_minutes
        )
        db_booking = crud.create_booking(db=db, booking=booking_data, owner_id=owner.id)

        notifications.send_booking_confirmation(
            booking=db_booking.__dict__,
            owner_email=owner.email,
            owner_phone=owner.phone,
            owner_name=owner.name,
            business_name=owner.business_name,
            customer_email=customer_email,
            customer_phone=customer_phone,
            language=request.cookies.get("lang", "en")
        )

        template = env.get_template("booking_confirmation.html")
        return template.render(request=request, booking=db_booking, owner=owner)
    except Exception as e:
        return env.get_template("booking_page.html").render(
            request=request, owner=owner, services=[schemas.Service(**s) for s in owner.services_json], 
            availability=owner.availability_json, error_message=f"Error processing booking: {e}")

@app.post("/set-language")
async def set_language(response: Response, lang: str = Form(...)):
    response.set_cookie(key="lang", value=lang, httponly=False, samesite="Lax", max_age=3600*24*30)
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
