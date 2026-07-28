from fastapi import FastAPI, Depends, HTTPException, status, Request, Response, Form
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import timedelta, datetime
import json
import os
from typing import List, Optional

from . import models, schemas, crud, security, notifications
from .database import SessionLocal, engine
from .config import settings
from .i18n_config import get_jinja_env

models.Base.metadata.create_all(bind=engine)

app = FastAPI()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

async def get_current_owner(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = security.decode_access_token(token)
        owner_email: str = payload.get("sub")
        if owner_email is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        owner = crud.get_owner_by_email(db, owner_email)
        if owner is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return owner
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Could not validate credentials: {e}",
            headers={"WWW-Authenticate": "Bearer"},
        )

def get_templates(request: Request):
    locale = request.cookies.get("lang", "en")
    return get_jinja_env(locale)

@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    templates = get_templates(request)
    return templates.get_template("index.html").render({"request": request})

@app.get("/signup", response_class=HTMLResponse)
async def signup_form(request: Request):
    templates = get_templates(request)
    return templates.get_template("signup.html").render({"request": request})

@app.post("/signup", response_class=HTMLResponse)
async def signup(request: Request, db: Session = Depends(get_db),
                 name: str = Form(...), email: str = Form(...), password: str = Form(...),
                 business_name: str = Form(...), slug: str = Form(...), phone: str = Form(...)):
    templates = get_templates(request)
    owner = crud.get_owner_by_email(db, email)
    if owner:
        return templates.get_template("signup.html").render({"request": request, "error": "Email already registered"})
    owner_by_slug = crud.get_owner_by_slug(db, slug)
    if owner_by_slug:
        return templates.get_template("signup.html").render({"request": request, "error": "Business URL slug already taken"})

    owner_data = schemas.OwnerCreate(
        name=name, email=email, password=password,
        business_name=business_name, slug=slug, phone=phone
    )
    db_owner = crud.create_owner(db=db, owner=owner_data)
    
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": db_owner.email}, expires_delta=access_token_expires
    )
    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    response.set_cookie(key="access_token", value=access_token, httponly=True, max_age=access_token_expires.total_seconds())
    return response

@app.get("/login", response_class=HTMLResponse)
async def login_form(request: Request):
    templates = get_templates(request)
    return templates.get_template("login.html").render({"request": request})

@app.post("/login", response_class=HTMLResponse)
async def login(request: Request, db: Session = Depends(get_db),
                email: str = Form(...), password: str = Form(...)):
    templates = get_templates(request)
    owner = crud.authenticate_owner(db, email, password)
    if not owner:
        return templates.get_template("login.html").render({"request": request, "error": "Incorrect email or password"})
    
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": owner.email}, expires_delta=access_token_expires
    )
    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    response.set_cookie(key="access_token", value=access_token, httponly=True, max_age=access_token_expires.total_seconds())
    return response

@app.get("/logout")
async def logout(response: Response):
    response.delete_cookie(key="access_token")
    return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)

@app.get("/dashboard", response_class=HTMLResponse)
async def owner_dashboard(request: Request, db: Session = Depends(get_db),
                          current_owner: models.Owner = Depends(get_current_owner)):
    templates = get_templates(request)
    
    services = json.loads(current_owner.services_json) if current_owner.services_json else []
    availability = json.loads(current_owner.availability_json) if current_owner.availability_json else {}

    upcoming_bookings = db.query(models.Booking).filter(
        models.Booking.owner_id == current_owner.id,
        models.Booking.booking_date >= datetime.now().date()
    ).order_by(models.Booking.booking_date, models.Booking.booking_time).all()

    return templates.get_template("dashboard.html").render(
        {"request": request, "owner": current_owner, "services": services,
         "availability": availability, "upcoming_bookings": upcoming_bookings}
    )

@app.post("/dashboard/profile", response_class=HTMLResponse)
async def update_profile(request: Request, db: Session = Depends(get_db),
                         current_owner: models.Owner = Depends(get_current_owner),
                         name: str = Form(...), business_name: str = Form(...), phone: str = Form(...),
                         services_json: str = Form("[]"), availability_json: str = Form("{}")):
    templates = get_templates(request)
    
    owner_update = schemas.OwnerProfileUpdate(name=name, business_name=business_name, phone=phone)
    updated_owner = crud.update_owner_profile(db, current_owner, owner_update)
    
    try:
        validated_services = json.loads(services_json)
        if not isinstance(validated_services, list) or \
           not all(isinstance(s, dict) and 'name' in s and 'duration' in s for s in validated_services):
            raise ValueError("Invalid services format")
        current_owner.services_json = json.dumps(validated_services)
    except json.JSONDecodeError:
        return templates.get_template("dashboard.html").render(
            {"request": request, "owner": current_owner, "error": "Invalid JSON format for services."}
        )
    except ValueError as e:
        return templates.get_template("dashboard.html").render(
            {"request": request, "owner": current_owner, "error": f"Invalid services data: {e}"}
        )

    try:
        validated_availability = json.loads(availability_json)
        if not isinstance(validated_availability, dict):
            raise ValueError("Invalid availability format")
        current_owner.availability_json = json.dumps(validated_availability)
    except json.JSONDecodeError:
        return templates.get_template("dashboard.html").render(
            {"request": request, "owner": current_owner, "error": "Invalid JSON format for availability."}
        )
    except ValueError as e:
        return templates.get_template("dashboard.html").render(
            {"request": request, "owner": current_owner, "error": f"Invalid availability data: {e}"}
        )

    db.add(current_owner)
    db.commit()
    db.refresh(current_owner)

    upcoming_bookings = db.query(models.Booking).filter(
        models.Booking.owner_id == current_owner.id,
        models.Booking.booking_date >= datetime.now().date()
    ).order_by(models.Booking.booking_date, models.Booking.booking_time).all()

    return templates.get_template("dashboard.html").render(
        {"request": request, "owner": updated_owner, "services": validated_services,
         "availability": validated_availability, "upcoming_bookings": upcoming_bookings,
         "message": "Profile updated successfully!"}
    )


@app.get("/bookslot.app/{owner_slug}", response_class=HTMLResponse)
async def public_booking_page(request: Request, owner_slug: str, db: Session = Depends(get_db)):
    templates = get_templates(request)
    owner = crud.get_owner_by_slug(db, owner_slug)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Owner not found")

    services = json.loads(owner.services_json) if owner.services_json else []
    availability = json.loads(owner.availability_json) if owner.availability_json else {}
    
    return templates.get_template("booking_page.html").render(
        {"request": request, "owner": owner, "services": services, "availability": availability}
    )

@app.post("/bookslot.app/{owner_slug}/book", response_class=HTMLResponse)
async def submit_booking(request: Request, owner_slug: str, db: Session = Depends(get_db),
                         customer_name: str = Form(...), customer_email: str = Form(...),
                         customer_phone: str = Form(...), service_name: str = Form(...),
                         booking_date: str = Form(...), booking_time: str = Form(...)):
    templates = get_templates(request)
    owner = crud.get_owner_by_slug(db, owner_slug)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Owner not found")

    try:
        booking_datetime_str = f"{booking_date} {booking_time}"
        parsed_booking_datetime = datetime.strptime(booking_datetime_str, "%Y-%m-%d %H:%M")
        
        booking_schema = schemas.BookingCreate(
            customer_name=customer_name,
            customer_email=customer_email,
            customer_phone=customer_phone,
            service_name=service_name,
            booking_date=parsed_booking_datetime.date(),
            booking_time=parsed_booking_datetime.time()
        )
        
        db_booking = crud.create_booking(db=db, booking=booking_schema, owner_id=owner.id)

        await notifications.send_booking_confirmation_email_to_customer(
            customer_email, owner.business_name, service_name, booking_datetime_str
        )
        await notifications.send_new_booking_notification_to_owner(
            owner.email, owner.phone, owner.business_name, customer_name, customer_email,
            customer_phone, service_name, booking_datetime_str
        )

        return templates.get_template("booking_confirmation.html").render(
            {"request": request, "owner": owner, "booking": db_booking}
        )
    except ValueError as e:
        return templates.get_template("booking_page.html").render(
            {"request": request, "owner": owner, "error": f"Invalid booking details: {e}"}
        )
    except Exception as e:
        print(f"Booking submission error: {e}")
        return templates.get_template("booking_page.html").render(
            {"request": request, "owner": owner, "error": "An unexpected error occurred during booking. Please try again."}
        )

@app.get("/set_language/{lang}")
async def set_language(lang: str, response: Response, request: Request):
    response.set_cookie(key="lang", value=lang, httponly=False)
    referer = request.headers.get("referer", "/")
    return RedirectResponse(url=referer, status_code=status.HTTP_302_FOUND)