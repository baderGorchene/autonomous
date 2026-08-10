from fastapi import FastAPI, Depends, HTTPException, status, Request, Response
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session, joinedload
from datetime import timedelta, date, datetime
from typing import List, Annotated, Optional
from gettext import gettext as _
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func

from . import models, schemas, security, notifications, analytics, availability_utils
from .database import SessionLocal, engine, get_db, Base
from .config import settings

Base.metadata.create_all(bind=engine)

app = FastAPI()

app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def get_current_owner(token: Annotated[str, Depends(oauth2_scheme)], db: Session = Depends(get_db)):
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
    owner = db.query(models.Owner).filter(models.Owner.email == email).first()
    if owner is None:
        raise credentials_exception
    return owner

def get_current_customer(token: Annotated[str, Depends(oauth2_scheme)], db: Session = Depends(get_db)):
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
    customer = db.query(models.Customer).filter(models.Customer.email == email).first()
    if customer is None:
        raise credentials_exception
    return customer


@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.post("/owner/signup", response_model=schemas.OwnerResponse)
def create_owner(owner: schemas.OwnerCreate, db: Session = Depends(get_db)):
    db_owner = db.query(models.Owner).filter(models.Owner.email == owner.email).first()
    if db_owner:
        raise HTTPException(status_code=400, detail="Email already registered")
    hashed_password = security.get_password_hash(owner.password)
    db_owner = models.Owner(email=owner.email, hashed_password=hashed_password, name=owner.name, phone=owner.phone)
    db.add(db_owner)
    db.commit()
    db.refresh(db_owner)
    return db_owner

@app.post("/owner/token", response_model=schemas.Token)
def login_for_access_token(form_data: Annotated[OAuth2PasswordRequestForm, Depends()], db: Session = Depends(get_db)):
    owner = db.query(models.Owner).filter(models.Owner.email == form_data.username).first()
    if not owner or not security.verify_password(form_data.password, owner.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": owner.email, "type": "owner"}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/customer/signup", response_model=schemas.CustomerResponse)
def create_customer(customer: schemas.CustomerCreate, db: Session = Depends(get_db)):
    db_customer = db.query(models.Customer).filter(models.Customer.email == customer.email).first()
    if db_customer:
        raise HTTPException(status_code=400, detail="Email already registered")
    hashed_password = security.get_password_hash(customer.password)
    db_customer = models.Customer(email=customer.email, hashed_password=hashed_password, name=customer.name, phone=customer.phone)
    db.add(db_customer)
    db.commit()
    db.refresh(db_customer)
    return db_customer

@app.post("/customer/token", response_model=schemas.Token)
def customer_login_for_access_token(form_data: Annotated[OAuth2PasswordRequestForm, Depends()], db: Session = Depends(get_db)):
    customer = db.query(models.Customer).filter(models.Customer.email == form_data.username).first()
    if not customer or not security.verify_password(form_data.password, customer.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": customer.email, "type": "customer"}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


@app.post("/services/{service_id}/reviews", response_model=schemas.ReviewResponse, status_code=status.HTTP_201_CREATED)
def submit_review_for_service(
    service_id: int,
    review_data: schemas.ReviewCreate,
    current_customer: Annotated[models.Customer, Depends(get_current_customer)],
    db: Session = Depends(get_db)
):
    service = db.query(models.Service).filter(models.Service.id == service_id).first()
    if not service:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")

    db_review = models.Review(
        service_id=service_id,
        customer_id=current_customer.id,
        rating=review_data.rating,
        comment=review_data.comment
    )
    db.add(db_review)
    db.commit()
    db.refresh(db_review);

    review_response = schemas.ReviewResponse.from_orm(db_review)
    review_response.customer_name = current_customer.name if current_customer.name else current_customer.email
    return review_response

@app.get("/services/{service_id}/reviews", response_model=List[schemas.ReviewResponse])
def get_reviews_for_service(
    service_id: int,
    db: Session = Depends(get_db)
):
    service = db.query(models.Service).filter(models.Service.id == service_id).first()
    if not service:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")

    reviews = db.query(models.Review).filter(models.Review.service_id == service_id).options(
        joinedload(models.Review.customer)
    ).all()

    response_reviews = []
    for review in reviews:
        review_response = schemas.ReviewResponse.from_orm(review)
        if review.customer:
            review_response.customer_name = review.customer.name if review.customer.name else review.customer.email
        else:
            review_response.customer_name = "Anonymous"
        response_reviews.append(review_response)
    
    return response_reviews

@app.get("/customers/{customer_id}/reviews", response_model=List[schemas.ReviewResponse])
def get_reviews_by_customer(
    customer_id: int,
    current_customer: Annotated[models.Customer, Depends(get_current_customer)],
    db: Session = Depends(get_db)
):
    if customer_id != current_customer.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view these reviews")

    reviews = db.query(models.Review).filter(models.Review.customer_id == customer_id).options(
        joinedload(models.Review.service)
    ).all()

    response_reviews = []
    for review in reviews:
        review_response = schemas.ReviewResponse.from_orm(review)
        review_response.customer_name = current_customer.name if current_customer.name else current_customer.email
        response_reviews.append(review_response)
    
    return response_reviews

@app.middleware("http")
async def add_i18n_middleware(request: Request, call_next):
    response = await call_next(request)
    return response

@app.get("/bookslot/{owner_name}", response_class=HTMLResponse)
async def booking_page(owner_name: str, request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse("booking_page.html", {"request": request, "owner_name": owner_name})

@app.post("/bookslot/{owner_name}/book", response_model=schemas.BookingResponse)
async def submit_booking(owner_name: str, booking: schemas.BookingCreate, db: Session = Depends(get_db)):
    owner = db.query(models.Owner).filter(models.Owner.name == owner_name).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")
    service = db.query(models.Service).filter(models.Service.id == booking.service_id, models.Service.owner_id == owner.id).first()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found for this owner")

    existing_booking = db.query(models.Booking).filter(
        models.Booking.service_id == booking.service_id,
        models.Booking.date == booking.date,
        models.Booking.time == booking.time
    ).first()
    if existing_booking:
        raise HTTPException(status_code=400, detail="Slot already booked")

    customer = db.query(models.Customer).filter(models.Customer.email == booking.customer_email).first()
    customer_id = None
    if customer:
        customer_id = customer.id

    db_booking = models.Booking(
        owner_id=owner.id,
        service_id=booking.service_id,
        customer_id=customer_id,
        customer_name=booking.customer_name,
        customer_email=booking.customer_email,
        customer_phone=booking.customer_phone,
        date=booking.date,
        time=booking.time,
        status=models.BookingStatus.CONFIRMED
    )
    db.add(db_booking)
    db.commit()
    db.refresh(db_booking)

    return db_booking

@app.get("/booking_confirmation", response_class=HTMLResponse)
async def booking_confirmation_page(request: Request):
    return templates.TemplateResponse("booking_confirmation.html", {"request": request})

@app.get("/owner/dashboard", response_class=HTMLResponse)
async def owner_dashboard(request: Request, current_owner: Annotated[models.Owner, Depends(get_current_owner)]):
    return templates.TemplateResponse("dashboard.html", {"request": request, "owner": current_owner})

@app.post("/stripe-webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    return {"status": "success"}

@app.get("/owner/analytics/monthly_bookings", response_model=List[dict])
async def get_monthly_bookings(current_owner: Annotated[models.Owner, Depends(get_current_owner)], db: Session = Depends(get_db)):
    return analytics.get_monthly_bookings_data(db, current_owner.id)

@app.get("/owner/analytics/popular_services", response_model=List[dict])
async def get_popular_services(current_owner: Annotated[models.Owner, Depends(get_current_owner)], db: Session = Depends(get_db)):
    return analytics.get_popular_services_data(db, current_owner.id)