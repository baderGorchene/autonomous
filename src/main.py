from fastapi import FastAPI, Depends, HTTPException, status, Request, Form, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import json
import os
from urllib.parse import urlencode

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

def get_current_owner(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
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

def get_jinja_env_with_locale(request: Request):
    locale = request.cookies.get("locale", "en")
    return get_jinja_env(locale)

@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request, jinja_env: Any = Depends(get_jinja_env_with_locale)):
    template = jinja_env.get_template("index.html")
    return template.render({"request": request})

@app.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request, jinja_env: Any = Depends(get_jinja_env_with_locale)):
    template = jinja_env.get_template("signup.html")
    return template.render({"request": request, "error": None})

@app.post("/signup", response_class=HTMLResponse)
async def signup_owner(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    business_name: str = Form(...),
    slug: str = Form(...),
    phone: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    jinja_env: Any = Depends(get_jinja_env_with_locale)
):
    template = jinja_env.get_template("signup.html")
    owner = crud.get_owner_by_email(db, email=email)
    if owner:
        return template.render({"request": request, "error": "Email already registered"})
    
    owner_by_slug = crud.get_owner_by_slug(db, slug=slug)
    if owner_by_slug:
        return template.render({"request": request, "error": "Slug already taken"})

    try:
        owner_create = schemas.OwnerCreate(
            name=name, email=email, password=password, business_name=business_name, slug=slug, phone=phone
        )
        crud.create_owner(db=db, owner=owner_create);
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    except Exception as e:
        return template.render({"request": request, "error": f"An error occurred: {e}"})

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, jinja_env: Any = Depends(get_jinja_env_with_locale)):
    template = jinja_env.get_template("login.html")
    return template.render({"request": request, "error": None})

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

@app.post("/login", response_class=RedirectResponse)
async def login_owner(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
    jinja_env: Any = Depends(get_jinja_env_with_locale)
):
    owner = crud.authenticate_owner(db, email, password)
    if not owner:
        template = jinja_env.get_template("login.html")
        return HTMLResponse(template.render({"request": request, "error": "Incorrect email or password"}), status_code=status.HTTP_401_UNAUTHORIZED)
    
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": owner.email}, expires_delta=access_token_expires
    )
    
    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    response.set_cookie(key="access_token", value=access_token, httponly=True, max_age=access_token_expires.total_seconds())
    return response

@app.get("/logout", response_class=RedirectResponse)
async def logout_owner():
    response = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    response.delete_cookie(key="access_token")
    return response

@app.get("/dashboard", response_class=HTMLResponse)
async def owner_dashboard(
    request: Request,
    current_owner: schemas.Owner = Depends(get_current_owner),
    db: Session = Depends(get_db),
    jinja_env: Any = Depends(get_jinja_env_with_locale)
):
    template = jinja_env.get_template("dashboard.html")
    
    upcoming_bookings = db.query(models.Booking).filter(
        models.Booking.owner_id == current_owner.id,
        models.Booking.booking_time >= datetime.now()
    ).order_by(models.Booking.booking_time).all()

    services = json.loads(current_owner.services_json) if current_owner.services_json else []
    availability = json.loads(current_owner.availability_json) if current_owner.availability_json else {}
    
    return template.render({
        "request": request,
        "owner": current_owner,
        "upcoming_bookings": upcoming_bookings,
        "services": services,
        "availability": availability,
        "error": None,
        "success": None
    })

@app.post("/dashboard/update_profile", response_class=HTMLResponse)
async def update_owner_profile(
    request: Request,
    name: str = Form(...),
    business_name: str = Form(...),
    phone: Optional[str] = Form(None),
    services_json: str = Form(...),
    availability_json: str = Form(...),
    current_owner: models.Owner = Depends(get_current_owner),
    db: Session = Depends(get_db),
    jinja_env: Any = Depends(get_jinja_env_with_locale)
):
    template = jinja_env.get_template("dashboard.html")
    error_message = None
    success_message = None

    try:
        parsed_services = json.loads(services_json)
        validated_services = [schemas.Service(**s) for s in parsed_services]
        
        parsed_availability = json.loads(availability_json)
        validated_availability = {
            day: schemas.DayAvailability(**data) 
            for day, data in parsed_availability.items()
        }

        owner_update_schema = schemas.OwnerProfileUpdate(
            name=name,
            business_name=business_name,
            phone=phone,
            services=validated_services,
            availability=validated_availability
        )
        
        updated_owner = crud.update_owner_profile(db, current_owner, owner_update_schema)
        updated_owner.services_json = json.dumps([s.dict() for s in validated_services])
        updated_owner.availability_json = json.dumps({day: data.dict() for day, data in validated_availability.items()})
        db.add(updated_owner)
        db.commit()
        db.refresh(updated_owner)
        
        success_message = "Profile updated successfully!"

    except json.JSONDecodeError:
        error_message = "Invalid JSON format for services or availability."
    except Exception as e:
        error_message = f"An error occurred during profile update: {e}"

    upcoming_bookings = db.query(models.Booking).filter(
        models.Booking.owner_id == current_owner.id,
        models.Booking.booking_time >= datetime.now()
    ).order_by(models.Booking.booking_time).all()
    
    services = json.loads(current_owner.services_json) if current_owner.services_json else []
    availability = json.loads(current_owner.availability_json) if current_owner.availability_json else {}

    return template.render({
        "request": request,
        "owner": current_owner,
        "upcoming_bookings": upcoming_bookings,
        "services": services,
        "availability": availability,
        "error": error_message,
        "success": success_message
    })


@app.get("/bookslot.app/{owner_slug}", response_class=HTMLResponse)
async def public_booking_page(
    request: Request,
    owner_slug: str,
    db: Session = Depends(get_db),
    jinja_env: Any = Depends(get_jinja_env_with_locale)
):
    owner = crud.get_owner_by_slug(db, slug=owner_slug)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Owner not found")

    services = json.loads(owner.services_json) if owner.services_json else []
    availability = json.loads(owner.availability_json) if owner.availability_json else {}

    template = jinja_env.get_template("booking_page.html")
    return template.render({
        "request": request,
        "owner": owner,
        "services": services,
        "availability": availability,
        "error": None
    })

@app.post("/bookslot.app/{owner_slug}/book", response_class=HTMLResponse)
async def submit_booking(
    request: Request,
    owner_slug: str,
    customer_name: str = Form(...),
    customer_email: str = Form(...),
    customer_phone: Optional[str] = Form(None),
    service_name: str = Form(...),
    booking_date: str = Form(...),
    booking_time: str = Form(...),
    db: Session = Depends(get_db),
    jinja_env: Any = Depends(get_jinja_env_with_locale)
):
    owner = crud.get_owner_by_slug(db, slug=owner_slug);
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Owner not found")

    template = jinja_env.get_template("booking_page.html")
    
    try:
        combined_booking_datetime_str = f"{booking_date} {booking_time}"
        parsed_booking_time = datetime.strptime(combined_booking_datetime_str, "%Y-%m-%d %H:%M")

        if parsed_booking_time <= datetime.now():
            services = json.loads(owner.services_json) if owner.services_json else []
            availability = json.loads(owner.availability_json) if owner.availability_json else {}
            return HTMLResponse(template.render({
                "request": request,
                "owner": owner,
                "services": services,
                "availability": availability,
                "error": "Booking time must be in the future."
            }), status_code=status.HTTP_400_BAD_REQUEST)

        booking_create = schemas.BookingCreate(
            customer_name=customer_name,
            customer_email=customer_email,
            customer_phone=customer_phone,
            service_name=service_name,
            booking_time=parsed_booking_time
        )
        db_booking = crud.create_booking(db=db, booking=booking_create, owner_id=owner.id)

        notifications.send_booking_confirmation_email(
            recipient_email=customer_email,
            owner_name=owner.business_name,
            customer_name=customer_name,
            service_name=service_name,
            booking_time=parsed_booking_time,
            is_owner=False
        )
        if customer_phone:
            notifications.send_whatsapp_notification(
                recipient_phone=customer_phone,
                owner_name=owner.business_name,
                customer_name=customer_name,
                service_name=service_name,
                booking_time=parsed_booking_time,
                is_owner=False
            )

        notifications.send_booking_confirmation_email(
            recipient_email=owner.email,
            owner_name=owner.name,
            customer_name=customer_name,
            service_name=service_name,
            booking_time=parsed_booking_time,
            is_owner=True
        )
        if owner.phone:
            notifications.send_whatsapp_notification(
                recipient_phone=owner.phone,
                owner_name=owner.name,
                customer_name=customer_name,
                service_name=service_name,
                booking_time=parsed_booking_time,
                is_owner=True
            )

        return RedirectResponse(url=f"/bookslot.app/{owner.slug}/confirmation", status_code=status.HTTP_302_FOUND)

    except ValueError:
        services = json.loads(owner.services_json) if owner.services_json else []
        availability = json.loads(owner.availability_json) if owner.availability_json else {}
        return HTMLResponse(template.render({
            "request": request,
            "owner": owner,
            "services": services,
            "availability": availability,
            "error": "Invalid date or time format."
        }), status_code=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        services = json.loads(owner.services_json) if owner.services_json else []
        availability = json.loads(owner.availability_json) if owner.availability_json else {}
        return HTMLResponse(template.render({
            "request": request,
            "owner": owner,
            "services": services,
            "availability": availability,
            "error": f"An unexpected error occurred: {e}"
        }), status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

@app.get("/bookslot.app/{owner_slug}/confirmation", response_class=HTMLResponse)
async def booking_confirmation_page(
    request: Request,
    owner_slug: str,
    db: Session = Depends(get_db),
    jinja_env: Any = Depends(get_jinja_env_with_locale)
):
    owner = crud.get_owner_by_slug(db, slug=owner_slug);
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Owner not found")

    template = jinja_env.get_template("booking_confirmation.html")
    return template.render({"request": request, "owner": owner})


@app.get("/static/{filepath:path}")
async def static_files(filepath: str):
    return Response(content=f"Serving static file: {filepath}", media_type="text/plain")

@app.post("/set-locale", response_class=RedirectResponse)
async def set_locale(request: Request, locale: str = Form(...)):
    referer = request.headers.get("referer", "/")
    response = RedirectResponse(url=referer, status_code=status.HTTP_302_FOUND)
    response.set_cookie(key="locale", value=locale, max_age=3600 * 24 * 30)
    return response
