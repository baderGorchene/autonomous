from fastapi import FastAPI, Depends, HTTPException, status, Request, Form, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from datetime import timedelta, datetime
import json
import os
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

from . import crud, models, schemas, security, notifications
from .database import SessionLocal, engine
from .config import settings
from .i18n_config import get_jinja_env

models.Base.metadata.create_all(bind=engine)

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_templates(request: Request):
    locale = request.cookies.get("locale", "en")
    if 'lang' in request.query_params:
        locale = request.query_params['lang']
    return get_jinja_env(locale)

@app.post("/token", response_model=schemas.Token)
async def login_for_access_token(db: Session = Depends(get_db), form_data: OAuth2PasswordRequestForm = Depends()):
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

async def get_current_owner(db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = security.decode_access_token(token)
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except Exception:
        raise credentials_exception
    owner = crud.get_owner_by_email(db, email=email)
    if owner is None:
        raise credentials_exception
    return owner

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request, templates: Environment = Depends(get_templates)):
    return templates.get_template("index.html").render({"request": request})

@app.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request, templates: Environment = Depends(get_templates)):
    return templates.get_template("signup.html").render({"request": request})

@app.post("/signup", response_class=HTMLResponse)
async def create_owner_account(request: Request,
                               name: str = Form(...),
                               business_name: str = Form(...),
                               email: str = Form(...),
                               password: str = Form(...),
                               db: Session = Depends(get_db),
                               templates: Environment = Depends(get_templates)):
    db_owner = crud.get_owner_by_email(db, email=email)
    if db_owner:
        return templates.get_template("signup.html").render({"request": request, "error": "Email already registered"})
    
    slug = business_name.lower().replace(" ", "-")
    
    owner_in = schemas.OwnerCreate(name=name, business_name=business_name, email=email, password=password, slug=slug)
    crud.create_owner(db=db, owner=owner_in)
    
    return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, templates: Environment = Depends(get_templates)):
    return templates.get_template("login.html").render({"request": request})

@app.post("/login", response_class=HTMLResponse)
async def process_login(request: Request,
                        email: str = Form(...),
                        password: str = Form(...),
                        db: Session = Depends(get_db),
                        templates: Environment = Depends(get_templates)):
    owner = crud.authenticate_owner(db, email, password)
    if not owner:
        return templates.get_template("login.html").render({"request": request, "error": "Invalid email or password"})

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": owner.email}, expires_delta=access_token_expires
    )
    
    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(key="access_token", value=access_token, httponly=True, expires=access_token_expires.total_seconds())
    return response

@app.get("/logout")
async def logout(response: Response):
    response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(key="access_token")
    return response

@app.get("/book/{owner_slug}", response_class=HTMLResponse)
async def get_booking_page(owner_slug: str, request: Request, db: Session = Depends(get_db), templates: Environment = Depends(get_templates)):
    owner = crud.get_owner_by_slug(db, slug=owner_slug)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Owner not found")
    
    services = json.loads(owner.services_json) if owner.services_json else []
    availability = json.loads(owner.availability_json) if owner.availability_json else {}
    
    return templates.get_template("booking_page.html").render({
        "request": request,
        "owner": owner,
        "services": services,
        "availability": availability
    })

@app.post("/book/{owner_slug}", response_class=HTMLResponse)
async def submit_booking(
    owner_slug: str,
    request: Request,
    customer_name: str = Form(...),
    customer_email: str = Form(...),
    customer_phone: str = Form(...),
    service_name: str = Form(...),
    booking_date: str = Form(...),
    booking_time: str = Form(...),
    db: Session = Depends(get_db),
    templates: Environment = Depends(get_templates)
):
    owner = crud.get_owner_by_slug(db, slug=owner_slug)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Owner not found")

    try:
        booking_datetime_str = f"{booking_date} {booking_time}"
        booking_datetime = datetime.strptime(booking_datetime_str, "%Y-%m-%d %H:%M")
    except ValueError:
        return templates.get_template("booking_page.html").render({
            "request": request,
            "owner": owner,
            "services": json.loads(owner.services_json),
            "availability": json.loads(owner.availability_json),
            "error": "Invalid date or time format."
        })

    booking_in = schemas.BookingCreate(
        customer_name=customer_name,
        customer_email=customer_email,
        customer_phone=customer_phone,
        service_name=service_name,
        booking_time=booking_datetime,
        status="pending"
    )
    
    try:
        booking = crud.create_booking(db=db, booking=booking_in, owner_id=owner.id)
        
        notifications.send_owner_notification(owner, booking)
        notifications.send_customer_confirmation(owner, booking)

        return templates.get_template("booking_confirmation.html").render({
            "request": request,
            "owner": owner,
            "booking": booking
        })
    except Exception as e:
        return templates.get_template("booking_page.html").render({
            "request": request,
            "owner": owner,
            "services": json.loads(owner.services_json),
            "availability": json.loads(owner.availability_json),
            "error": f"An error occurred during booking: {e}"
        })

@app.get("/dashboard", response_class=HTMLResponse)
async def owner_dashboard(request: Request,
                          current_owner: models.Owner = Depends(get_current_owner),
                          db: Session = Depends(get_db),
                          templates: Environment = Depends(get_templates)):
    
    upcoming_bookings = db.query(models.Booking).filter(
        models.Booking.owner_id == current_owner.id,
        models.Booking.booking_time >= datetime.now()
    ).order_by(models.Booking.booking_time).all()

    services = json.loads(current_owner.services_json) if current_owner.services_json else []
    availability = json.loads(current_owner.availability_json) if current_owner.availability_json else {}

    return templates.get_template("dashboard.html").render({
        "request": request,
        "owner": current_owner,
        "upcoming_bookings": upcoming_bookings,
        "services": services,
        "availability": availability,
        "slug": current_owner.slug
    })

@app.post("/dashboard/profile", response_class=HTMLResponse)
async def update_owner_profile_endpoint(
    request: Request,
    name: str = Form(...),
    business_name: str = Form(...),
    phone: str = Form(""),
    services_json: str = Form("[]"),
    availability_json: str = Form("{}"),
    current_owner: models.Owner = Depends(get_current_owner),
    db: Session = Depends(get_db),
    templates: Environment = Depends(get_templates)
):
    try:
        services = json.loads(services_json)
        availability = json.loads(availability_json)
        
        owner_update = schemas.OwnerProfileUpdate(
            name=name,
            business_name=business_name,
            phone=phone,
            services_json=json.dumps(services),
            availability_json=json.dumps(availability)
        )
        
        updated_owner = crud.update_owner_profile(db, current_owner, owner_update)
        
        current_owner.services_json = owner_update.services_json
        current_owner.availability_json = owner_update.availability_json
        db.add(current_owner)
        db.commit()
        db.refresh(current_owner)

        return RedirectResponse(url="/dashboard?message=Profile updated successfully", status_code=status.HTTP_303_SEE_OTHER)
    except json.JSONDecodeError:
        return templates.get_template("dashboard.html").render({
            "request": request,
            "owner": current_owner,
            "error": "Invalid JSON format for services or availability.",
            "upcoming_bookings": [],
            "services": json.loads(current_owner.services_json) if current_owner.services_json else [],
            "availability": json.loads(current_owner.availability_json) if current_owner.availability_json else {}
        })
    except Exception as e:
        return templates.get_template("dashboard.html").render({
            "request": request,
            "owner": current_owner,
            "error": f"An error occurred: {e}",
            "upcoming_bookings": [],
            "services": json.loads(current_owner.services_json) if current_owner.services_json else [],
            "availability": json.loads(current_owner.availability_json) if current_owner.availability_json else {}
        })

@app.get("/set-language/{lang}")
async def set_language(lang: str, request: Request, response: Response):
    referer = request.headers.get("referer", "/")
    
    parsed_url = urlparse(referer)
    query_params = parse_qs(parsed_url.query)
    query_params['lang'] = [lang]
    new_query = urlencode(query_params, doseq=True)
    
    new_url = urlunparse(parsed_url._replace(query=new_query))

    response = RedirectResponse(url=new_url, status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(key="locale", value=lang, httponly=False, max_age=3600 * 24 * 30)
    return response

@app.get("/health")
async def health_check():
    return {"status": "ok"}
