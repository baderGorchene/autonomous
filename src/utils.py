from datetime import datetime, timedelta
from typing import List, Optional
import calendar

def generate_recurring_dates(
    start_time: datetime,
    duration_minutes: int,
    recurrence_pattern: str,
    recurrence_end_date: Optional[datetime] = None,
    recurrence_end_count: Optional[int] = None,
    max_bookings: int = 52
) -> List[tuple[datetime, datetime]]:
    """
    Generates a list of (start_time, end_time) tuples for recurring bookings.
    """
    bookings = []
    current_start_time = start_time
    count = 0

    while True:
        if recurrence_end_count is not None and count >= recurrence_end_count:
            break
        if recurrence_end_date is not None and current_start_time.date() > recurrence_end_date.date():
            break
        if count >= max_bookings:
            break

        current_end_time = current_start_time + timedelta(minutes=duration_minutes)
        bookings.append((current_start_time, current_end_time))
        count += 1

        if recurrence_pattern == "DAILY":
            current_start_time += timedelta(days=1)
        elif recurrence_pattern == "WEEKLY":
            current_start_time += timedelta(weeks=1)
        elif recurrence_pattern == "MONTHLY":
            current_month = current_start_time.month
            current_year = current_start_time.year
            current_day = current_start_time.day
            
            new_month = current_month + 1
            new_year = current_year
            if new_month > 12:
                new_month = 1
                new_year += 1
            
            try:
                current_start_time = current_start_time.replace(year=new_year, month=new_month)
            except ValueError:
                last_day_of_month = calendar.monthrange(new_year, new_month)[1]
                current_start_time = current_start_time.replace(year=new_year, month=new_month, day=last_day_of_month)
        else:
            break 
            
    return bookings
