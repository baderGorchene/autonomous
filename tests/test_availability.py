from datetime import date
from src.availability_utils import get_available_slots_for_day
from src import models

def test_availability_empty(db_session):
    slots = get_available_slots_for_day(
        db=db_session,
        owner_id=1,
        service_id=1,
        target_date=date(2025, 5, 1),
        slot_duration_minutes=30
    )
    assert slots == []
