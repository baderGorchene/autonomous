from fastapi import FastAPI, Depends, HTTPException, status, Request, Response
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import timedelta, date, datetime
from typing import List, Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from starlette.responses import HTMLResponse, RedirectResponse
from starlette.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from gettext import gettext as _
import gettext
import os
import calendar
import stripe

from . import models, schemas, security, notifications, availability_utils, analytics
from .database import SessionLocal, engine
from .config import settings

models.Base.metadata.create_all(bind=engine)

app = FastAPI()

app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

templates = Jinja2Templates(directory="templates")

LOCALE_DIR = "locales"
LANGUAGES = {"en": "English", "ar": "العربية", "fr": "Français"}

def i18n_filter(text):
    return _(text)

def format_currency(value, currency_code, locale_code):
    if locale_code == 'ar':
        return f"{value:,.2f} {currency_code}"
    return f"{currency_code} {value:,.2f}"

templates.env.filters['i18n'] = i18n_filter
templates.env.filters['format_currency'] = format_currency


@app.middleware("http")
async def setup_locale(request: Request, call_next):
    lang_code = request.session.get("lang", "en")
    
    if 'lang' in request.query_params:
        new_lang = request.query_params['lang']
        if new_lang in LANGUAGES:
            lang_code = new_lang
            request.session["lang"] = new_lang
            response = RedirectResponse(request.url.remove_query_params(keys=["lang"]))
            response.set_cookie(key="lang", value=lang_code, httponly=True)
            return response
    
    if "lang" not in request.session and "lang" in request.cookies:
        lang_code = request.cookies["lang"]
        request.session["lang"] = lang_code

    try:
        t = gettext.translation("messages", LOCALE_DIR, languages=[lang_code])
        t.install()
        request.state.lang_code = lang_code
    except Exception as e:
        print(f"Error loading translation for {lang_code}: {e}")
        t = gettext.translation("messages", LOCALE_DIR, languages=["en"])
        t.install()
        request.state.lang_code = "en"

    response = await call_next(request)
    response.set_cookie(key="lang", value=lang_code, httponly=True)
    return response

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

stripe.api_key = settings.STRIPE_API_KEY

oauth2_scheme_owner = OAuth2PasswordBearer(tokenUrl="owner/token")

oauth2_scheme_customer = OAuth2PasswordBearer(tokenUrl="customer/token")

def get_current_owner(db: Session = Depends(get_db), token: str = Depends(oauth2_scheme_owner)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    return security.get_owner_from_token(db, token, credentials_exception)

def get_current_customer(db: Session = Depends(get_db), token: str = Depends(oauth2_scheme_customer)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    return security.get_customer_from_token(db, token, credentials_exception)

def get_current_active_owner(current_owner: models.Owner = Depends(get_current_owner)):
    return current_owner

def get_current_active_customer(current_customer: models.Customer = Depends(get_current_customer)):
    return current_customer

@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.post("/owner/signup", response_model=schemas.OwnerOut)
def register_owner(owner: schemas.OwnerCreate, db: Session = Depends(get_db)):
    db_owner = db.query(models.Owner).filter(models.Owner.email == owner.email).first()
    if db_owner:
        raise HTTPException(status_code=400, detail=_("Email already registered"))
    hashed_password = security.get_password_hash(owner.password)
    db_owner = models.Owner(email=owner.email, name=owner.name, phone=owner.phone, hashed_password=hashed_password)
    db.add(db_owner)
    db.commit()
    db.refresh(db_owner)
    return db_owner

@app.post("/owner/token", response_model=schemas.Token)
async def owner_login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    owner = security.authenticate_owner(db, form_data.username, form_data.password)
    if not owner:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_("Incorrect email or password"),
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_owner_access_token(
        data={"sub": owner.email}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/owner/me", response_model=schemas.OwnerOut)
def read_owner_me(current_owner: models.Owner = Depends(get_current_active_owner)):
    return current_owner

@app.put("/owner/me", response_model=schemas.OwnerOut)
def update_owner_profile(owner_update: schemas.OwnerProfileUpdate, db: Session = Depends(get_db), current_owner: models.Owner = Depends(get_current_active_owner)):
    if owner_update.email and owner_update.email != current_owner.email:
        existing_owner = db.query(models.Owner).filter(models.Owner.email == owner_update.email).first()
        if existing_owner:
            raise HTTPException(status_code=400, detail=_("Email already registered by another owner"))

    for field, value in owner_update.dict(exclude_unset=True).items():
        setattr(current_owner, field, value)
    db.commit()
    db.refresh(current_owner)
    return current_owner

@app.post("/customer/signup", response_model=schemas.CustomerOut)
def register_customer(customer: schemas.CustomerCreate, db: Session = Depends(get_db)):
    db_customer = db.query(models.Customer).filter(models.Customer.email == customer.email).first()
    if db_customer:
        raise HTTPException(status_code=400, detail=_("Email already registered"))
    hashed_password = security.get_password_hash(customer.password)
    db_customer = models.Customer(email=customer.email, name=customer.name, phone=customer.phone, hashed_password=hashed_password)
    db.add(db_customer)
    db.commit()
    db.refresh(db_customer)
    return db_customer

@app.post("/customer/token", response_model=schemas.Token)
async def customer_login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    customer = security.authenticate_customer(db, form_data.username, form_data.password)
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_("Incorrect email or password"),
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_customer_access_token(
        data={"sub": customer.email}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/customer/me", response_model=schemas.CustomerOut)
def read_customer_me(current_customer: models.Customer = Depends(get_current_active_customer)):
    return current_customer

@app.put("/customer/me", response_model=schemas.CustomerOut)
def update_customer_profile(customer_update: schemas.CustomerProfileUpdate, db: Session = Depends(get_db), current_customer: models.Customer = Depends(get_current_active_customer)):
    if customer_update.email and customer_update.email != current_customer.email:
        existing_customer = db.query(models.Customer).filter(models.Customer.email == customer_update.email).first()
        if existing_customer:
            raise HTTPException(status_code=400, detail=_("Email already registered by another customer"))

    for field, value in customer_update.dict(exclude_unset=True).items():
        setattr(current_customer, field, value)
    db.commit()
    db.refresh(current_customer)
    return current_customer

@app.post("/owner/services/", response_model=schemas.ServiceOut)
def create_service_for_owner(
    service: schemas.ServiceCreate,
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(get_current_active_owner),
):
    db_service = models.Service(**service.dict(), owner_id=current_owner.id)
    db.add(db_service)
    db.commit()
    db.refresh(db_service)
    return db_service

@app.get("/owner/services/", response_model=List[schemas.ServiceOut])
def read_owner_services(
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(get_current_active_owner),
):
    services = db.query(models.Service).filter(models.Service.owner_id == current_owner.id).all()
    return services

@app.get("/owner/services/{service_id}", response_model=schemas.ServiceOut)
def read_owner_service(
    service_id: int,
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(get_current_active_owner),
):
    service = db.query(models.Service).filter(models.Service.id == service_id, models.Service.owner_id == current_owner.id).first()
    if service is None:
        raise HTTPException(status_code=404, detail=_("Service not found"))
    return service

@app.put("/owner/services/{service_id}", response_model=schemas.ServiceOut)
def update_owner_service(
    service_id: int,
    service_update: schemas.ServiceCreate,
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(get_current_active_owner),
):
    db_service = db.query(models.Service).filter(models.Service.id == service_id, models.Service.owner_id == current_owner.id).first()
    if db_service is None:
        raise HTTPException(status_code=404, detail=_("Service not found"))
    for field, value in service_update.dict(exclude_unset=True).items():
        setattr(db_service, field, value)
    db.commit()
    db.refresh(db_service)
    return db_service

@app.delete("/owner/services/{service_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_owner_service(
    service_id: int,
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(get_current_active_owner),
):
    db_service = db.query(models.Service).filter(models.Service.id == service_id, models.Service.owner_id == current_owner.id).first()
    if db_service is None:
        raise HTTPException(status_code=404, detail=_("Service not found"))
    db.delete(db_service)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@app.post("/owner/availabilities/", response_model=schemas.AvailabilityOut)
def create_availability_for_owner(
    availability: schemas.AvailabilityCreate,
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(get_current_active_owner),
):
    db_availability = models.Availability(**availability.dict(), owner_id=current_owner.id)
    db.add(db_availability)
    db.commit()
    db.refresh(db_availability)
    return db_availability

@app.get("/owner/availabilities/", response_model=List[schemas.AvailabilityOut])
def read_owner_availabilities(
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(get_current_active_owner),
    service_id: Optional[int] = None,
    date: Optional[date] = None,
):
    query = db.query(models.Availability).filter(models.Availability.owner_id == current_owner.id)
    if service_id:
        query = query.filter(models.Availability.service_id == service_id)
    if date:
        query = query.filter(models.Availability.date == date)
    availabilities = query.all()
    return availabilities

@app.get("/{owner_name}", response_class=HTMLResponse)
async def public_booking_page(owner_name: str, request: Request, db: Session = Depends(get_db)):
    db_owner = db.query(models.Owner).filter(func.lower(models.Owner.name) == func.lower(owner_name)).first()
    if not db_owner:
        raise HTTPException(status_code=404, detail=_("Owner not found"))

    services = db.query(models.Service).filter(models.Service.owner_id == db_owner.id).all()
    
    services_with_reviews = []
    for service in services:
        reviews = db.query(models.Review).filter(models.Review.service_id == service.id).all()
        review_count = len(reviews)
        average_rating = sum(r.rating for r in reviews) / review_count if review_count > 0 else None
        
        review_outs = []
        for r in reviews:
            customer = db.query(models.Customer).filter(models.Customer.id == r.customer_id).first()
            review_outs.append(schemas.ReviewOut(
                id=r.id,
                service_id=r.service_id,
                customer_id=r.customer_id,
                rating=r.rating,
                comment=r.comment,
                created_at=r.created_at,
                customer_name=customer.name if customer else "Anonymous"
            ))

        services_with_reviews.append(schemas.ServiceOut(
            id=service.id,
            owner_id=service.owner_id,
            name=service.name,
            description=service.description,
            duration_minutes=service.duration_minutes,
            price=service.price,
            currency=service.currency,
            average_rating=average_rating,
            review_count=review_count,
            reviews=review_outs
        ))

    return templates.TemplateResponse(
        "booking_page.html",
        {
            "request": request,
            "owner": db_owner,
            "services": services_with_reviews,
            "lang_code": request.state.lang_code,
            "languages": LANGUAGES,
            "gettext": _
        }
    )

@app.get("/{owner_name}/booking_confirmation", response_class=HTMLResponse)
async def booking_confirmation_page(owner_name: str, request: Request, db: Session = Depends(get_db)):
    db_owner = db.query(models.Owner).filter(func.lower(models.Owner.name) == func.lower(owner_name)).first()
    if not db_owner:
        raise HTTPException(status_code=404, detail=_("Owner not found"))
    
    return templates.TemplateResponse(
        "booking_confirmation.html",
        {
            "request": request,
            "owner": db_owner,
            "lang_code": request.state.lang_code,
            "languages": LANGUAGES,
            "gettext": _
        }
    )

@app.post("/book", response_model=schemas.BookingOut)
async def create_booking(booking: schemas.BookingCreate, db: Session = Depends(get_db)):
    service = db.query(models.Service).filter(models.Service.id == booking.service_id).first()
    if not service:
        raise HTTPException(status_code=404, detail=_("Service not found"))

    customer_id = None
    db_customer = db.query(models.Customer).filter(models.Customer.email == booking.customer_email).first()
    if db_customer:
        customer_id = db_customer.id
    
    available_slots = availability_utils.get_available_slots_for_day(
        db, service.owner_id, service.id, booking.date, service.duration_minutes
    )
    if booking.time not in available_slots:
        raise HTTPException(status_code=400, detail=_("Selected time slot is not available or already booked."))

    if booking.is_recurring:
        pass

    db_booking = models.Booking(
        owner_id=service.owner_id,
        service_id=booking.service_id,
        customer_id=customer_id,
        customer_name=booking.customer_name,
        customer_email=booking.customer_email,
        customer_phone=booking.customer_phone,
        date=booking.date,
        time=booking.time,
        status=models.BookingStatus.CONFIRMED,
        is_recurring=booking.is_recurring
    )
    db.add(db_booking)
    db.commit()
    db.refresh(db_booking)

    owner = db.query(models.Owner).filter(models.Owner.id == service.owner_id).first()
    if owner:
        notifications.send_booking_confirmation_to_owner(owner, db_booking, service)
        notifications.send_booking_confirmation_to_customer(db_booking, service)

    return db_booking

@app.get("/owner/dashboard", response_class=HTMLResponse)
async def owner_dashboard(request: Request, db: Session = Depends(get_db), current_owner: models.Owner = Depends(get_current_active_owner)):
    upcoming_bookings = db.query(models.Booking).filter(
        models.Booking.owner_id == current_owner.id,
        models.Booking.date >= date.today()
    ).order_by(models.Booking.date, models.Booking.time).all()

    services_map = {service.id: service for service in db.query(models.Service).filter(models.Service.owner_id == current_owner.id).all()}

    monthly_bookings_data = analytics.get_monthly_bookings_data(db, current_owner.id)
    popular_services_data = analytics.get_popular_services_data(db, current_owner.id)

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "owner": current_owner,
            "upcoming_bookings": upcoming_bookings,
            "services_map": services_map,
            "lang_code": request.state.lang_code,
            "languages": LANGUAGES,
            "monthly_bookings_data": monthly_bookings_data,
            "popular_services_data": popular_services_data,
            "gettext": _
        }
    )

@app.get("/owner/analytics/monthly_bookings", response_model=List[dict])
def get_owner_monthly_bookings(db: Session = Depends(get_db), current_owner: models.Owner = Depends(get_current_active_owner)):
    return analytics.get_monthly_bookings_data(db, current_owner.id)

@app.get("/owner/analytics/popular_services", response_model=List[dict])
def get_owner_popular_services(db: Session = Depends(get_db), current_owner: models.Owner = Depends(get_current_active_owner)):
    return analytics.get_popular_services_data(db, current_owner.id)

@app.post("/owner/create-checkout-session")
async def create_checkout_session(db: Session = Depends(get_db), current_owner: models.Owner = Depends(get_current_active_owner)):
    if current_owner.subscription_status == models.SubscriptionStatus.PREMIUM:
        raise HTTPException(status_code=400, detail=_("Owner is already a premium subscriber."))

    try:
        checkout_session = stripe.checkout.Session.create(
            line_items=[
                {
                    'price': settings.STRIPE_PREMIUM_PRICE_ID,
                    'quantity': 1,
                },
            ],
            mode='subscription',
            success_url=f"http://localhost:8000/owner/dashboard?success=true",
            cancel_url=f"http://localhost:8000/owner/dashboard?canceled=true",
            customer=current_owner.stripe_customer_id if current_owner.stripe_customer_id else None,
            client_reference_id=str(current_owner.id),
            metadata={"owner_id": str(current_owner.id)},
        )
        return {"url": checkout_session.url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/stripe-webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get('stripe-signature')

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except stripe.error.SignatureVerificationError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        owner_id = session.get('client_reference_id')
        customer_stripe_id = session.get('customer')

        if owner_id:
            owner = db.query(models.Owner).filter(models.Owner.id == int(owner_id)).first()
            if owner:
                owner.subscription_status = models.SubscriptionStatus.PREMIUM
                owner.stripe_customer_id = customer_stripe_id
                db.commit()

    return {"status": "success"}

def get_admin_user():
    return {"username": "admin"}

@app.get("/admin/owners", response_model=List[schemas.OwnerOut])
def list_owners(db: Session = Depends(get_db), admin: dict = Depends(get_admin_user)):
    owners = db.query(models.Owner).all()
    return owners

@app.get("/admin/owners/{owner_id}", response_model=schemas.OwnerOut)
def get_owner_by_id(owner_id: int, db: Session = Depends(get_db), admin: dict = Depends(get_admin_user)):
    owner = db.query(models.Owner).filter(models.Owner.id == owner_id).first()
    if not owner:
        raise HTTPException(status_code=404, detail=_("Owner not found"))
    return owner

@app.put("/admin/owners/{owner_id}", response_model=schemas.OwnerOut)
def update_owner_by_id(owner_id: int, owner_update: schemas.OwnerProfileUpdate, db: Session = Depends(get_db), admin: dict = Depends(get_admin_user)):
    owner = db.query(models.Owner).filter(models.Owner.id == owner_id).first()
    if not owner:
        raise HTTPException(status_code=404, detail=_("Owner not found"))
    
    if owner_update.email and owner_update.email != owner.email:
        existing_owner = db.query(models.Owner).filter(models.Owner.email == owner_update.email).first()
        if existing_owner and existing_owner.id != owner_id:
            raise HTTPException(status_code=400, detail=_("Email already registered by another owner"))

    for field, value in owner_update.dict(exclude_unset=True).items():
        setattr(owner, field, value)
    db.commit()
    db.refresh(owner)
    return owner

@app.delete("/admin/owners/{owner_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_owner_by_id(owner_id: int, db: Session = Depends(get_db), admin: dict = Depends(get_admin_user)):
    owner = db.query(models.Owner).filter(models.Owner.id == owner_id).first()
    if not owner:
        raise HTTPException(status_code=404, detail=_("Owner not found"))
    db.delete(owner)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@app.post("/services/{service_id}/reviews", response_model=schemas.ReviewOut, status_code=status.HTTP_201_CREATED)
def create_review_for_service(
    service_id: int,
    review: schemas.ReviewCreate,
    db: Session = Depends(get_db),
    current_customer: models.Customer = Depends(get_current_active_customer)
):
    service = db.query(models.Service).filter(models.Service.id == service_id).first()
    if not service:
        raise HTTPException(status_code=404, detail=_("Service not found"))

    booking_exists = db.query(models.Booking).filter(
        models.Booking.customer_id == current_customer.id,
        models.Booking.service_id == service_id,
        models.Booking.status == models.BookingStatus.COMPLETED
    ).first()

    if not booking_exists:
        raise HTTPException(status_code=403, detail=_("You can only review services you have booked and completed."))
    
    existing_review = db.query(models.Review).filter(
        models.Review.customer_id == current_customer.id,
        models.Review.service_id == service_id
    ).first()

    if existing_review:
        raise HTTPException(status_code=409, detail=_("You have already submitted a review for this service."))

    db_review = models.Review(
        service_id=service_id,
        customer_id=current_customer.id,
        rating=review.rating,
        comment=review.comment
    )
    db.add(db_review)
    db.commit()
    db.refresh(db_review)

    db_review.customer_name = current_customer.name
    return db_review

@app.get("/services/{service_id}/reviews", response_model=List[schemas.ReviewOut])
def get_reviews_for_service(
    service_id: int,
    db: Session = Depends(get_db)
):
    service = db.query(models.Service).filter(models.Service.id == service_id).first()
    if not service:
        raise HTTPException(status_code=404, detail=_("Service not found"))
    
    reviews = db.query(models.Review).filter(models.Review.service_id == service_id).all()
    
    review_outs = []
    for r in reviews:
        customer = db.query(models.Customer).filter(models.Customer.id == r.customer_id).first()
        review_outs.append(schemas.ReviewOut(
            id=r.id,
            service_id=r.service_id,
            customer_id=r.customer_id,
            rating=r.rating,
            comment=r.comment,
            created_at=r.created_at,
            customer_name=customer.name if customer else "Anonymous"
        ))
    return review_outs

@app.get("/services/{service_id}/ratings_summary", response_model=dict)
def get_service_ratings_summary(service_id: int, db: Session = Depends(get_db)):
    service = db.query(models.Service).filter(models.Service.id == service_id).first()
    if not service:
        raise HTTPException(status_code=404, detail=_("Service not found"))

    review_data = db.query(
        func.avg(models.Review.rating).label("average_rating"),
        func.count(models.Review.id).label("review_count")
    ).filter(models.Review.service_id == service_id).first()

    average_rating = review_data.average_rating if review_data.average_rating else None
    review_count = review_data.review_count if review_data.review_count else 0

    return {
        "service_id": service_id,
        "average_rating": average_rating,
        "review_count": review_count
    }
