from fastapi import FastAPI, Depends, HTTPException, status, APIRouter, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, date, time, timedelta
from typing import List, Optional

from . import models, schemas
from .database import get_db, init_db
from .security import get_current_owner
from .config import settings

app = FastAPI(title="BookSlot API")

@app.on_event("startup")
async def startup_event():
    await init_db()

router = APIRouter()

def generate_recurring_slots(
    availability_rule: models.OwnerAvailability,
    service_duration_minutes: int,
    query_start_date: date,
    query_end_date: date,
) -> list[datetime]:
    """Generates a list of potential booking slots based on a recurring availability rule."""
    slots = []
    
    rule_effective_start_date = availability_rule.start_date if availability_rule.start_date else date.min
    rule_effective_end_date = availability_rule.end_date if availability_rule.end_date else date.max

    effective_start_date = max(query_start_date, rule_effective_start_date)
    effective_end_date = min(query_end_date, rule_effective_end_date)

    if effective_start_date > effective_end_date:
        return []

    current_date = effective_start_date

    while current_date <= effective_end_date:
        is_available_today = False
        
        if availability_rule.recurrence_type == "one_off":
            if availability_rule.start_date and availability_rule.start_date == current_date:
                is_available_today = True
        elif availability_rule.recurrence_type == "daily":
            is_available_today = True
        elif availability_rule.recurrence_type == "weekly":
            if availability_rule.day_of_week is not None and current_date.weekday() == availability_rule.day_of_week:
                is_available_today = True

        if is_available_today:
            current_time_dt = datetime.combine(current_date, availability_rule.start_time)
            end_of_availability_dt = datetime.combine(current_date, availability_rule.end_time)

            while current_time_dt + timedelta(minutes=service_duration_minutes) <= end_of_availability_dt:
                slots.append(current_time_dt)
                current_time_dt += timedelta(minutes=service_duration_minutes)

        current_date += timedelta(days=1)

    return slots

@router.get("/services/{service_id}/available-slots", response_model=List[datetime])
async def get_available_slots(
    service_id: int,
    start_date: date = Query(..., description="Start date for availability query (YYYY-MM-DD)"),
    end_date: date = Query(..., description="End date for availability query (YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_db),
    current_owner: models.Owner = Depends(get_current_owner)
):
    """
    Retrieves available booking slots for a specific service and date range,
    considering recurring availability rules and existing bookings.
    """
    service_result = await db.execute(select(models.Service).filter(
        models.Service.id == service_id,
        models.Service.owner_id == current_owner.id
    ))
    service = service_result.scalar_one_or_none()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found or not owned by current owner")

    availability_rules_result = await db.execute(
        select(models.OwnerAvailability).filter(models.OwnerAvailability.owner_id == current_owner.id)
    )
    availability_rules = availability_rules_result.scalars().all()

    all_potential_slots: list[datetime] = []
    for rule in availability_rules:
        all_potential_slots.extend(
            generate_recurring_slots(rule, service.duration_minutes, start_date, end_date)
        )

    all_potential_slots = sorted(list(set(all_potential_slots)))

    booked_slots_result = await db.execute(
        select(models.Booking)
        .filter(
            models.Booking.service_id == service_id,
            models.Booking.booking_time >= datetime.combine(start_date, time.min),
            models.Booking.booking_time < datetime.combine(end_date + timedelta(days=1), time.min)
        )
    )
    booked_bookings = booked_slots_result.scalars().all()

    available_slots = []
    for potential_slot in all_potential_slots:
        is_booked = False
        for booking in booked_bookings:
            booking_start = booking.booking_time
            booking_end = booking_start + timedelta(minutes=service.duration_minutes)
            
            potential_slot_end = potential_slot + timedelta(minutes=service.duration_minutes)

            if not (potential_slot_end <= booking_start or potential_slot >= booking_end):
                is_booked = True
                break
        
        if not is_booked:
            available_slots.append(potential_slot)
            
    return available_slots

app.include_router(router, prefix="/api", tags=["Bookings"])
