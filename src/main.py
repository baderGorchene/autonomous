from fastapi import FastAPI, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from gettext import gettext as _
from datetime import datetime, date, timedelta, time
from dateutil.relativedelta import relativedelta
import uuid
from typing import List, Optional

from . import crud, models, schemas, security, notifications
from .database import engine, get_db
from .config import settings

models.Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="BookSlot API",
    description="API for BookSlot - a dead-simple booking page for local service businesses.",
    version="0.1.0",
)

# Main API router
router = FastAPI(docs_url="/api/docs", openapi_url="/api/openapi.json")

# --- Health Check ---
@router.get("/health", tags=["Health Check"])
async def health_check():
    return {"status": "ok", "message": "BookSlot API is up and running!"}

# --- Auth Endpoints ---
@router.post("/token", response_model=schemas.Token, tags=["Auth"])
async def login_for_access_token(form_data: security.OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    owner = security.authenticate_owner(db, form_data.username, form_data.password)
    if not owner:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_("Incorrect email or password"),
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": owner.email}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/owners/signup", response_model=schemas.OwnerInDB, status_code=status.HTTP_201_CREATED, tags=["Auth"])
async def create_owner_signup(owner: schemas.OwnerCreate, db: Session = Depends(get_db)):
    db_owner = crud.get_owner_by_email(db, email=owner.email)
    if db_owner:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_("Email already registered"))
    hashed_password = security.get_password_hash(owner.password)
    db_owner = models.Owner(email=owner.email, hashed_password=hashed_password, full_name=owner.full_name, phone_number=owner.phone_number)
    return crud.create_owner(db=db, owner=db_owner)

@router.get("/owners/me", response_model=schemas.OwnerInDB, tags=["Owners"])
async def read_owners_me(current_owner: schemas.OwnerInDB = Depends(security.get_current_active_owner)):
    return current_owner

# --- Service Endpoints ---
@router.post("/services/", response_model=schemas.ServiceInDB, status_code=status.HTTP_201_CREATED, tags=["Services"])
async def create_service_for_owner(
    service: schemas.ServiceCreate, db: Session = Depends(get_db),
    current_owner: schemas.OwnerInDB = Depends(security.get_current_active_owner)
):
    return crud.create_owner_service(db=db, service=service, owner_id=current_owner.id)

@router.get("/services/me", response_model=List[schemas.ServiceInDB], tags=["Services"])
async def read_my_services(
    skip: int = 0, limit: int = 100, db: Session = Depends(get_db),
    current_owner: schemas.OwnerInDB = Depends(security.get_current_active_owner)
):
    services = crud.get_owner_services(db, owner_id=current_owner.id, skip=skip, limit=limit)
    return services

# --- Availability Endpoints ---
@router.post("/availabilities/", response_model=schemas.AvailabilityInDB, status_code=status.HTTP_201_CREATED, tags=["Availability"])
async def create_availability_for_owner(
    availability: schemas.AvailabilityCreate, db: Session = Depends(get_db),
    current_owner: schemas.OwnerInDB = Depends(security.get_current_active_owner)
):
    return crud.create_owner_availability(db=db, availability=availability, owner_id=current_owner.id)

@router.get("/availabilities/me", response_model=List[schemas.AvailabilityInDB], tags=["Availability"])
async def read_my_availabilities(
    skip: int = 0, limit: int = 100, db: Session = Depends(get_db),
    current_owner: schemas.OwnerInDB = Depends(security.get_current_active_owner)
):
    availabilities = crud.get_owner_availabilities(db, owner_id=current_owner.id, skip=skip, limit=limit)
    return availabilities

# --- Booking Endpoints ---
# Helper to check availability (can be moved to crud or a dedicated availability module)
def check_availability(db: Session, owner_id: uuid.UUID, service_id: uuid.UUID, proposed_start_time: datetime, proposed_end_time: datetime) -> bool:
    service = crud.get_service(db, service_id=service_id)
    if not service:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Service not found"))
    
    if service.owner_id != owner_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_("Service does not belong to this owner"))

    day_of_week = proposed_start_time.weekday()
    owner_availabilities = crud.get_availabilities_by_owner_and_day(db, owner_id, day_of_week)

    is_generally_available = False
    for avail in owner_availabilities:
        booking_start_time_only = proposed_start_time.time()
        booking_end_time_only = proposed_end_time.time()
        
        if avail.start_time <= booking_start_time_only and avail.end_time >= booking_end_time_only:
            is_generally_available = True
            break
    
    if not is_generally_available:
        return False

    overlapping_bookings = crud.get_overlapping_bookings(db, owner_id, service_id, proposed_start_time, proposed_end_time)
    if overlapping_bookings:
        return False

    return True

# Helper to generate recurring dates
def generate_recurring_dates(start_date: date, pattern: str, end_date: Optional[date] = None, count: Optional[int] = None) -> List[date]:
    dates = []
    current_date = start_date
    
    if pattern not in ["DAILY", "WEEKLY", "MONTHLY"]:
        raise ValueError("Unsupported recurrence pattern")

    i = 0
    MAX_RECURRING_BOOKINGS = 52
    
    while True:
        if end_date and current_date > end_date:
            break
        if count and i >= count:
            break
        if i >= MAX_RECURRING_BOOKINGS:
            break

        dates.append(current_date)

        if pattern == "DAILY":
            current_date += timedelta(days=1)
        elif pattern == "WEEKLY":
            current_date += timedelta(weeks=1)
        elif pattern == "MONTHLY":
            current_date += relativedelta(months=1)
        
        i += 1
    return dates

@router.post("/public/bookings/", response_model=List[schemas.BookingResponse], status_code=status.HTTP_201_CREATED, tags=["Bookings"])
async def create_public_booking(
    booking_in: schemas.BookingCreate, db: Session = Depends(get_db), request: Request = None
):
    service = crud.get_service(db, service_id=booking_in.service_id)
    if not service:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Service not found"))
    
    owner = crud.get_owner(db, owner_id=service.owner_id)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Owner not found for this service"))

    service_duration = timedelta(minutes=service.duration_minutes)
    
    created_bookings = []
    
    if booking_in.is_recurring:
        recurrence_id = uuid.uuid4()
        
        try:
            recurring_dates = generate_recurring_dates(
                booking_in.start_time.date(),
                booking_in.recurrence_pattern,
                booking_in.recurrence_ends_on,
                booking_in.recurrence_count
            )
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
        
        if not recurring_dates:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_("No valid recurring dates generated."))

        master_booking_created = False
        last_generated_date = None
        successful_recurrence_count = 0

        for i, booking_date in enumerate(recurring_dates):
            last_generated_date = booking_date
            current_booking_start_time = datetime.combine(booking_date, booking_in.start_time.time())
            current_booking_end_time = current_booking_start_time + service_duration

            if current_booking_start_time < datetime.utcnow():
                continue

            is_available = check_availability(db, owner.id, service.id, current_booking_start_time, current_booking_end_time)
            
            if is_available:
                booking_data = models.Booking(
                    owner_id=owner.id,
                    service_id=service.id,
                    customer_name=booking_in.customer_name,
                    customer_email=booking_in.customer_email,
                    customer_phone=booking_in.customer_phone,
                    start_time=current_booking_start_time,
                    end_time=current_booking_end_time,
                    recurrence_id=recurrence_id,
                    recurrence_pattern=booking_in.recurrence_pattern,
                )
                
                if not master_booking_created:
                    booking_data.is_master_booking = True
                    master_booking_created = True

                new_booking = crud.create_booking(db, booking_data)
                created_bookings.append(new_booking)
                successful_recurrence_count += 1
                
                notifications.send_booking_confirmation(new_booking, owner, service, request.url_for('get_booking_details', booking_id=new_booking.id))
        
        if created_bookings:
            final_recurrence_end_date = booking_in.recurrence_ends_on if booking_in.recurrence_ends_on else last_generated_date
            for booking in created_bookings:
                booking.recurrence_end_date = final_recurrence_end_date
                booking.recurrence_count = successful_recurrence_count
                db.add(booking)
            db.commit()

        if not created_bookings:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_("No recurring slots were available for the selected pattern."))
        
    else:
        booking_end_time = booking_in.start_time + service_duration

        if booking_in.start_time < datetime.utcnow():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_("Booking cannot be in the past."))

        is_available = check_availability(db, owner.id, service.id, booking_in.start_time, booking_end_time)

        if not is_available:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_("Selected time slot is not available."))

        booking_data = models.Booking(
            owner_id=owner.id,
            service_id=service.id,
            customer_name=booking_in.customer_name,
            customer_email=booking_in.customer_email,
            customer_phone=booking_in.customer_phone,
            start_time=booking_in.start_time,
            end_time=booking_end_time,
            is_master_booking=False
        )
        new_booking = crud.create_booking(db, booking_data)
        created_bookings.append(new_booking)
        notifications.send_booking_confirmation(new_booking, owner, service, request.url_for('get_booking_details', booking_id=new_booking.id))
    
    return [schemas.BookingResponse.model_validate(b) for b in created_bookings]

@router.get("/bookings/{booking_id}", response_model=schemas.BookingResponse, tags=["Bookings"])
async def get_booking_details(booking_id: uuid.UUID, db: Session = Depends(get_db)):
    booking = crud.get_booking(db, booking_id)
    if not booking:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Booking not found"))
    return booking

# Mount the router to the main app
app.include_router(router)
