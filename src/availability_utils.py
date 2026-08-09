from datetime import date, time, datetime, timedelta
from typing import List, Dict, Tuple, Optional
from sqlalchemy.orm import Session
from . import models, schemas
import calendar

def get_available_slots_for_day(
    db: Session,
    owner_id: int,
    service_id: int,
    target_date: date,
    slot_duration_minutes: int
) -> List[time]:
    """
    Calculates available time slots for a given owner, service, and date,
    considering both one-off and recurring availability rules,
    and existing bookings.
    """
    
    all_availabilities = db.query(models.Availability).filter(
        models.Availability.owner_id == owner_id,
        (models.Availability.service_id == service_id) | (models.Availability.service_id.is_(None))
    ).all()

    applicable_availabilities: List[models.Availability] = []

    for avail in all_availabilities:
        if avail.date == target_date: # One-off availability for this specific date
            applicable_availabilities.append(avail)
        elif avail.date is None: # Recurring availability
            # Check if recurrence has started
            if avail.recurrence_start_date and avail.recurrence_start_date > target_date:
                continue
            # Check if recurrence has ended
            if avail.recurrence_end_date and avail.recurrence_end_date < target_date:
                continue

            if avail.recurrence_type == models.RecurrenceType.DAILY:
                applicable_availabilities.append(avail)
            elif avail.recurrence_type == models.RecurrenceType.WEEKLY:
                if avail.recurrence_value:
                    weekdays = [d.strip().upper() for d in avail.recurrence_value.split(',')]
                    target_weekday_name = calendar.day_abbr[target_date.weekday()].upper() 
                    if target_weekday_name in weekdays:
                        applicable_availabilities.append(avail)
            elif avail.recurrence_type == models.RecurrenceType.MONTHLY:
                if avail.recurrence_value:
                    try:
                        day_of_month = int(avail.recurrence_value)
                        if target_date.day == day_of_month:
                            applicable_availabilities.append(avail)
                    except ValueError:
                        # Handle more complex monthly rules if needed, e.g., "first_monday"
                        pass

    if not applicable_availabilities:
        return [] # No availability defined for this day

    # Combine all applicable availability ranges for the day
    combined_time_ranges: List[Tuple[time, time]] = []
    for avail in applicable_availabilities:
        combined_time_ranges.append((avail.start_time, avail.end_time))

    # Sort and merge overlapping time ranges
    merged_ranges = []
    if combined_time_ranges:
        sorted_ranges = sorted(combined_time_ranges)
        current_start, current_end = sorted_ranges[0]

        for next_start, next_end in sorted_ranges[1:]:
            # If the next range starts before or at the current end, merge them
            if next_start <= current_end:
                current_end = max(current_end, next_end)
            else:
                merged_ranges.append((current_start, current_end))
                current_start, current_end = next_start, next_end
        merged_ranges.append((current_start, current_end))

    # 2. Get existing bookings for the target_date and service
    existing_bookings = db.query(models.Booking).filter(
        models.Booking.owner_id == owner_id,
        models.Booking.service_id == service_id,
        models.Booking.date == target_date
    ).all()

    booked_slots: List[Tuple[time, time]] = []
    for booking in existing_bookings:
        booking_start_dt = datetime.combine(target_date, booking.time)
        booking_end_dt = booking_start_dt + timedelta(minutes=slot_duration_minutes) # Assuming booking duration is service duration
        booked_slots.append((booking_start_dt.time(), booking_end_dt.time()))

    # 3. Generate potential slots from merged availability ranges
    potential_slots: List[time] = []
    for start_t, end_t in merged_ranges:
        current_slot_start_dt = datetime.combine(target_date, start_t)
        end_dt = datetime.combine(target_date, end_t)

        while current_slot_start_dt + timedelta(minutes=slot_duration_minutes) <= end_dt:
            potential_slots.append(current_slot_start_dt.time())
            current_slot_start_dt += timedelta(minutes=slot_duration_minutes)

    # 4. Filter out booked slots
    available_slots: List[time] = []
    for slot_time in potential_slots:
        slot_start_dt = datetime.combine(target_date, slot_time)
        slot_end_dt = slot_start_dt + timedelta(minutes=slot_duration_minutes)

        is_booked = False
        for booked_start, booked_end in booked_slots:
            booked_start_dt = datetime.combine(target_date, booked_start)
            booked_end_dt = datetime.combine(target_date, booked_end)
            
            # Check for overlap: [slot_start, slot_end) and [booked_start, booked_end)
            if max(slot_start_dt, booked_start_dt) < min(slot_end_dt, booked_end_dt):
                is_booked = True
                break
        
        if not is_booked:
            available_slots.append(slot_time)

    return sorted(list(set(available_slots))) # Return unique sorted times
