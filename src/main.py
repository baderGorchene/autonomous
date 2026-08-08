from fastapi import FastAPI, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import List, Optional
import uuid

from src import models, schemas, security, notifications
from src.database import SessionLocal, engine
from src.config import settings
from src.i18n import get_locale, _
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import jwt, JWTError
from starlette.requests import Request
from starlette.responses import Response

import stripe

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

async def get_current_owner(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
        token_data = schemas.TokenData(email=email)
    except JWTError:
        raise credentials_exception
    owner = db.query(models.Owner).filter(models.Owner.email == token_data.email).first()
    if owner is None:
        raise credentials_exception
    return owner

def is_owner_available(db: Session, owner_id: uuid.UUID, start_time: datetime, end_time: datetime):
    booking_day_of_week = start_time.weekday()

    booking_start_str = start_time.strftime("%H:%M")
    booking_end_str = end_time.strftime("%H:%M")

    availabilities = db.query(models.Availability).filter(
        models.Availability.owner_id == owner_id,
        models.Availability.day_of_week == booking_day_of_week
    ).all()

    is_available_in_schedule = False
    for avail in availabilities:
        if avail.start_time <= booking_start_str and avail.end_time >= booking_end_str:
            is_available_in_schedule = True
            break
    
    if not is_available_in_schedule:
        return False

    overlapping_bookings = db.query(models.Booking).filter(
        models.Booking.owner_id == owner_id,
        models.Booking.start_time < end_time,
        models.Booking.end_time > start_time,
        models.Booking.status != "cancelled"
    ).first()

    return overlapping_bookings is None

@app.post("/book/{owner_public_id}", response_model=List[schemas.BookingInDB], status_code=status.HTTP_201_CREATED)
async def create_booking(
    owner_public_id: uuid.UUID,
    booking: schemas.BookingCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    owner = db.query(models.Owner).filter(models.Owner.id == owner_public_id).first()
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Owner not found"))

    service = db.query(models.Service).filter(
        models.Service.id == booking.service_id,
        models.Service.owner_id == owner.id,
        models.Service.is_active == True
    ).first()
    if not service:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Service not found or not active"))

    expected_end_time = booking.start_time + timedelta(minutes=service.duration_minutes)
    if booking.end_time != expected_end_time:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_("Booking end time does not match service duration.")
        )

    bookings_to_create = []
    created_bookings_response = []

    if booking.is_recurring:
        if not booking.recurrence_pattern:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_("Recurrence pattern is required for recurring bookings."))
        if not booking.recurrence_end_date and not booking.recurrence_count:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_("Either recurrence end date or recurrence count is required for recurring bookings."))
        if booking.recurrence_end_date and booking.recurrence_end_date < booking.start_time:
             raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_("Recurrence end date cannot be before the start time."))
        if booking.recurrence_count is not None and booking.recurrence_count <= 0:
             raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_("Recurrence count must be positive."))

        current_start = booking.start_time
        current_end = booking.end_time
        recurrence_group_id = uuid.uuid4()
        count = 0

        while True:
            if booking.recurrence_end_date and current_start > booking.recurrence_end_date:
                break
            if booking.recurrence_count is not None and count >= booking.recurrence_count:
                break
            
            if is_owner_available(db, owner.id, current_start, current_end):
                new_booking = models.Booking(
                    owner_id=owner.id,
                    service_id=booking.service_id,
                    customer_name=booking.customer_name,
                    customer_email=booking.customer_email,
                    customer_phone=booking.customer_phone,
                    start_time=current_start,
                    end_time=current_end,
                    is_recurring=True,
                    recurrence_pattern=booking.recurrence_pattern,
                    recurrence_end_date=booking.recurrence_end_date,
                    recurrence_count=booking.recurrence_count,
                    recurrence_group_id=recurrence_group_id
                )
                bookings_to_create.append(new_booking)
            
            if booking.recurrence_pattern == "DAILY":
                current_start += timedelta(days=1)
                current_end += timedelta(days=1)
            elif booking.recurrence_pattern == "WEEKLY":
                current_start += timedelta(weeks=1)
                current_end += timedelta(weeks=1)
            elif booking.recurrence_pattern == "MONTHLY":
                try:
                    current_start = current_start.replace(month=current_start.month % 12 + 1)
                    current_end = current_end.replace(month=current_end.month % 12 + 1)
                except ValueError:
                    next_month = current_start.month % 12 + 1
                    next_year = current_start.year + (1 if next_month == 1 else 0)
                    last_day_of_next_month = (current_start.replace(month=next_month, year=next_year, day=1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)
                    current_start = current_start.replace(month=next_month, year=next_year, day=last_day_of_next_month.day)
                    current_end = current_end.replace(month=next_month, year=next_year, day=last_day_of_next_month.day)
            else:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_("Invalid recurrence pattern."))
            
            count += 1
            if count > 100 and booking.recurrence_count is None:
                break

        if not bookings_to_create:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_("No available slots found for the recurring booking series."))

        for new_booking in bookings_to_create:
            db.add(new_booking)
            db.flush()
            created_bookings_response.append(schemas.BookingInDB.from_orm(new_booking))
            background_tasks.add_task(
                notifications.send_booking_confirmation_emails,
                owner,
                service,
                new_booking,
                db
            )
            background_tasks.add_task(
                notifications.send_booking_confirmation_whatsapp,
                owner,
                service,
                new_booking,
                db
            )
        db.commit()

    else:
        if not is_owner_available(db, owner.id, booking.start_time, booking.end_time):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_("Selected time slot is not available or conflicts with an existing booking."))

        db_booking = models.Booking(
            owner_id=owner.id,
            service_id=booking.service_id,
            customer_name=booking.customer_name,
            customer_email=booking.customer_email,
            customer_phone=booking.customer_phone,
            start_time=booking.start_time,
            end_time=booking.end_time,
            is_recurring=False
        )
        db.add(db_booking)
        db.commit()
        db.refresh(db_booking)
        created_bookings_response.append(schemas.BookingInDB.from_orm(db_booking))

        background_tasks.add_task(
            notifications.send_booking_confirmation_emails,
            owner,
            service,
            db_booking,
            db
        )
        background_tasks.add_task(
            notifications.send_booking_confirmation_whatsapp,
            owner,
            service,
            db_booking,
            db
        )
    
    return created_bookings_response
