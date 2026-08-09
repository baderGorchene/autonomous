from fastapi import FastAPI, Depends, HTTPException, status, Request, APIRouter
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime, timedelta, date
import calendar

from . import models, schemas # Assuming security and notifications are imported where needed
from .database import SessionLocal, engine
from .config import settings
from .i18n import get_locale, _ # Assuming i18n setup

models.Base.metadata.create_all(bind=engine)

app = FastAPI()
router = APIRouter()

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Internationalization setup
@app.middleware("http")
async def add_i18n_middleware(request: Request, call_next):
    locale = get_locale(request)
    request.state.locale = locale
    response = await call_next(request)
    return response

# The booking endpoint
@app.post("/book/{owner_username}", response_model=List[schemas.BookingResponse], status_code=status.HTTP_201_CREATED)
async def create_booking(
    owner_username: str,
    booking_data: schemas.BookingCreate,
    request: Request,
    db: Session = Depends(get_db)
):
    owner = db.query(models.Owner).filter(models.Owner.name == owner_username).first()
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Owner not found"))

    service = db.query(models.Service).filter(models.Service.id == booking_data.service_id, models.Service.owner_id == owner.id).first()
    if not service:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Service not found for this owner"))

    start_dt_time = datetime.strptime(booking_data.start_time, "%H:%M").time()
    
    end_time_str = (datetime.combine(booking_data.booking_date, start_dt_time) + timedelta(minutes=service.duration_minutes)).strftime("%H:%M")

    bookings_to_commit = []

    if booking_data.is_recurring and booking_data.recurrence_pattern and booking_data.recurrence_end_date:
        current_booking_date = booking_data.booking_date
        
        # Max number of recurring instances to prevent abuse/errors
        max_recurrences = 365 * 2 # Roughly 2 years of daily bookings
        count = 0

        while current_booking_date <= booking_data.recurrence_end_date and count < max_recurrences:
            booking_instance_data = {
                "owner_id": owner.id,
                "service_id": booking_data.service_id,
                "customer_name": booking_data.customer_name,
                "customer_email": booking_data.customer_email,
                "customer_phone": booking_data.customer_phone,
                "booking_date": current_booking_date,
                "start_time": booking_data.start_time,
                "end_time": end_time_str,
                "status": "confirmed",
                "is_recurring": True,
                "recurrence_pattern": models.RecurrencePattern(booking_data.recurrence_pattern),
                "recurrence_end_date": datetime.combine(booking_data.recurrence_end_date, datetime.min.time())
            }
            
            new_booking = models.Booking(**booking_instance_data)
            bookings_to_commit.append(new_booking)

            # Advance to the next date based on recurrence pattern
            if booking_data.recurrence_pattern == "daily":
                current_booking_date += timedelta(days=1)
            elif booking_data.recurrence_pattern == "weekly":
                current_booking_date += timedelta(weeks=1)
            elif booking_data.recurrence_pattern == "bi-weekly":
                current_booking_date += timedelta(weeks=2)
            elif booking_data.recurrence_pattern == "monthly":
                year = current_booking_date.year
                month = current_booking_date.month + 1
                if month > 12:
                    month = 1
                    year += 1
                day = min(current_booking_date.day, calendar.monthrange(year, month)[1])
                current_booking_date = date(year, month, day)
            else:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_("Invalid recurrence pattern"))
            count += 1
        
        if count >= max_recurrences:
             raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_("Too many recurring bookings requested. Maximum 2 years of recurrence allowed."))

    else:
        # Single booking
        new_booking = models.Booking(
            owner_id=owner.id,
            service_id=booking_data.service_id,
            customer_name=booking_data.customer_name,
            customer_email=booking_data.customer_email,
            customer_phone=booking_data.customer_phone,
            booking_date=booking_data.booking_date,
            start_time=booking_data.start_time,
            end_time=end_time_str,
            status="confirmed",
            is_recurring=False
        )
        bookings_to_commit.append(new_booking)

    created_bookings_db = []
    try:
        if not bookings_to_commit:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_("No bookings to create."))

        # Handle parent booking for recurring series
        if booking_data.is_recurring:
            parent_booking_obj = bookings_to_commit[0]
            db.add(parent_booking_obj)
            db.flush() # Assigns an ID to parent_booking_obj
            parent_id = parent_booking_obj.id
            parent_booking_obj.parent_booking_id = parent_id # Parent points to itself
            created_bookings_db.append(parent_booking_obj)

            for i in range(1, len(bookings_to_commit)):
                bookings_to_commit[i].parent_booking_id = parent_id
                db.add(bookings_to_commit[i])
                created_bookings_db.append(bookings_to_commit[i])
        else:
            db.add(bookings_to_commit[0])
            created_bookings_db.append(bookings_to_commit[0])

        db.commit()

        for book in created_bookings_db:
            db.refresh(book)
            # Notifications will be handled later, potentially summarized for recurring series
            # For now, placeholder:
            # notifications.send_booking_confirmation_email(owner, book, service)
            # notifications.send_booking_confirmation_whatsapp(owner, book, service)

    except Exception as e:
        db.rollback()
        print(f"Error creating booking(s): {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"{_('Failed to create booking(s)')}: {str(e)}")

    return [schemas.BookingResponse.model_validate(book) for book in created_bookings_db]
