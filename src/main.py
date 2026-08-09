from fastapi import FastAPI, Depends, HTTPException, status, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session, joinedload
from datetime import date, time, datetime, timedelta
from typing import List, Optional
import calendar

from . import models, schemas, security, notifications, availability_utils, analytics
from .database import SessionLocal, engine
from .config import settings
from .i18n import get_locale, _
from starlette.requests import Request
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import JSONResponse
import stripe

models.Base.metadata.create_all(bind=engine)

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

stripe.api_key = settings.STRIPE_API_KEY

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Dependency for current owner
def get_current_owner(request: Request, db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    token = request.session.get("access_token") # Try getting from session first
    if not token:
        # Fallback to Authorization header if not in session (e.g., for API clients)
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
    
    if token is None:
        raise credentials_exception

    try:
        payload = security.decode_access_token(token)
        owner_email: str = payload.get("sub")
        if owner_email is None:
            raise credentials_exception
    except Exception:
        raise credentials_exception
    owner = db.query(models.Owner).filter(models.Owner.email == owner_email).first()
    if owner is None:
        raise credentials_exception
    return owner

@app.post("/token", response_model=schemas.Token)
async def login_for_access_token(request: Request, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    owner = security.authenticate_owner(db, form_data.username, form_data.password)
    if not owner:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = security.create_access_token(
        data={"sub": owner.email}
    )
    request.session["access_token"] = access_token # Store in session
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/logout")
async def logout(request: Request):
    request.session.pop("access_token", None)
    return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

@app.post("/owners/", response_model=schemas.Owner)
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

@app.get("/owners/{owner_id}/dashboard_data")
def get_owner_dashboard_data(
    owner_id: int,
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(get_current_owner)
):
    if current_owner.id != owner_id:
        raise HTTPException(status_code=403, detail="Not authorized to view this dashboard")
    
    owner = db.query(models.Owner).filter(models.Owner.id == owner_id).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")

    today = date.today()
    upcoming_bookings = db.query(models.Booking).filter(
        models.Booking.owner_id == owner_id,
        models.Booking.date >= today
    ).order_by(models.Booking.date, models.Booking.time).all()

    # Convert to schema for response
    upcoming_bookings_schemas = [schemas.Booking.from_orm(b) for b in upcoming_bookings]

    monthly_bookings_data = analytics.get_monthly_bookings_data(db, owner_id)
    popular_services_data = analytics.get_popular_services_data(db, owner_id)

    return {
        "owner_name": owner.name,
        "upcoming_bookings": upcoming_bookings_schemas,
        "monthly_bookings_data": monthly_bookings_data,
        "popular_services_data": popular_services_data
    }

@app.post("/owners/{owner_id}/bookings/", response_model=schemas.BookingBase)
def create_booking(
    owner_id: int,
    booking: schemas.BookingCreate,
    db: Session = Depends(get_db),
    current_owner: Optional[models.Owner] = Depends(get_current_owner) # Can be public or owner-initiated
):
    # If owner is logged in, verify they are the correct owner
    if current_owner and current_owner.id != owner_id:
        raise HTTPException(status_code=403, detail="Not authorized to create bookings for this owner")

    owner = db.query(models.Owner).filter(models.Owner.id == owner_id).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")

    service = db.query(models.Service).filter(models.Service.id == booking.service_id, models.Service.owner_id == owner_id).first()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found or does not belong to this owner")

    slot_duration = service.duration_minutes

    if booking.is_recurring:
        if not booking.recurrence_type or not booking.recurrence_end_date:
            raise HTTPException(status_code=400, detail="Recurring bookings require recurrence_type and recurrence_end_date")

        all_created_bookings = []
        current_date = booking.date
        while current_date <= booking.recurrence_end_date:
            create_this_instance = False
            if booking.recurrence_type == models.RecurrenceType.DAILY:
                create_this_instance = True
            elif booking.recurrence_type == models.RecurrenceType.WEEKLY:
                if booking.recurrence_value:
                    weekdays = [d.strip().upper() for d in booking.recurrence_value.split(',')]
                    target_weekday_name = calendar.day_abbr[current_date.weekday()].upper()
                    if target_weekday_name in weekdays:
                        create_this_instance = True
            elif booking.recurrence_type == models.RecurrenceType.MONTHLY:
                if booking.recurrence_value and str(current_date.day) == booking.recurrence_value:
                    create_this_instance = True
            
            if create_this_instance:
                # Check availability for this specific date
                available_slots = availability_utils.get_available_slots_for_day(
                    db, owner_id, service.id, current_date, slot_duration
                )
                if booking.time not in available_slots:
                    raise HTTPException(status_code=400, detail=f"Slot {booking.time.isoformat()} on {current_date.isoformat()} is not available or conflicts with another booking.")
                
                db_booking = models.Booking(
                    owner_id=owner_id,
                    service_id=service.id,
                    date=current_date,
                    time=booking.time,
                    customer_name=booking.customer_name,
                    customer_email=booking.customer_email,
                    customer_phone=booking.customer_phone,
                    is_recurring=True, # Mark individual instances as part of a recurring series
                    recurrence_type=booking.recurrence_type,
                    recurrence_value=booking.recurrence_value,
                    recurrence_end_date=booking.recurrence_end_date
                )
                db.add(db_booking)
                all_created_bookings.append(db_booking)
                notifications.send_booking_confirmation_email(
                    booking.customer_email, owner.email, owner.name, service.name, current_date, booking.time, booking.customer_name, is_recurring=True
                )
                notifications.send_booking_notification_whatsapp(
                    owner.phone, owner.name, service.name, current_date, booking.time, booking.customer_name, booking.customer_phone, is_recurring=True
                )

            current_date += timedelta(days=1)
        
        db.commit()
        for b in all_created_bookings:
            db.refresh(b)
        # Return the first created booking or a success message
        if all_created_bookings:
            return all_created_bookings[0] # Return the first one as representative
        else:
            raise HTTPException(status_code=400, detail="No bookings could be created based on recurrence rules.")

    else: # One-off booking
        available_slots = availability_utils.get_available_slots_for_day(
            db, owner_id, service.id, booking.date, slot_duration
        )
        if booking.time not in available_slots:
            raise HTTPException(status_code=400, detail=f"Slot {booking.time.isoformat()} on {booking.date.isoformat()} is not available or conflicts with another booking.")

        db_booking = models.Booking(
            owner_id=owner_id,
            service_id=service.id,
            date=booking.date,
            time=booking.time,
            customer_name=booking.customer_name,
            customer_email=booking.customer_email,
            customer_phone=booking.customer_phone,
            is_recurring=False
        )
        db.add(db_booking)
        db.commit()
        db.refresh(db_booking)

        notifications.send_booking_confirmation_email(
            booking.customer_email, owner.email, owner.name, service.name, booking.date, booking.time, booking.customer_name, is_recurring=False
        )
        notifications.send_booking_notification_whatsapp(
            owner.phone, owner.name, service.name, booking.date, booking.time, booking.customer_name, booking.customer_phone, is_recurring=False
        )
        return db_booking
