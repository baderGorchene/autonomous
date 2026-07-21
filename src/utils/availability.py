from datetime import datetime, timedelta
from typing import List, Dict

def get_available_slots(date: datetime, availability_config: Dict, existing_bookings: List[datetime], duration_minutes: int = 30) -> List[datetime]:
    day_of_week = date.strftime('%A').lower()
    config = availability_config.get(day_of_week)
    if not config or not config.get('is_open'):
        return []

    slots = []
    start_time = datetime.strptime(config['start'], '%H:%M').time()
    end_time = datetime.strptime(config['end'], '%H:%M').time()
    
    current_dt = datetime.combine(date.date(), start_time)
    end_dt = datetime.combine(date.date(), end_time)

    while current_dt + timedelta(minutes=duration_minutes) <= end_dt:
        if current_dt not in existing_bookings:
            slots.append(current_dt)
        current_dt += timedelta(minutes=duration_minutes)
    return slots

def validate_booking(requested_dt: datetime, availability_config: Dict, existing_bookings: List[datetime]) -> bool:
    available = get_available_slots(requested_dt, availability_config, existing_bookings)
    return requested_dt in available