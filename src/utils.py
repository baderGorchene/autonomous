from datetime import datetime, timedelta
from dateutil.rrule import rrule, MINUTELY
from sqlalchemy.orm import Session
from . import models

def get_available_slots(owner_id: int, date: datetime, db: Session):
    # Assumes owner.availability_json format: {'start_hour': 9, 'end_hour': 17, 'duration': 30}
    owner = db.query(models.Owner).filter(models.Owner.id == owner_id).first()
    avail = owner.availability_json or {'start_hour': 9, 'end_hour': 17, 'duration': 30}
    
    start = date.replace(hour=avail['start_hour'], minute=0, second=0, microsecond=0)
    end = date.replace(hour=avail['end_hour'], minute=0, second=0, microsecond=0)
    
    all_slots = list(rrule(MINUTELY, interval=avail['duration'], dtstart=start, until=end))
    
    # Filter out already booked slots
    booked = db.query(models.Booking.datetime).filter(models.Booking.owner_id == owner_id).all()
    booked_datetimes = {b[0] for b in booked}
    
    return [s for s in all_slots if s not in booked_datetimes and s < end]