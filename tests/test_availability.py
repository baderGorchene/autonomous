import pytest
from datetime import date, time, datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.models import Base, Owner, Service, Availability, Booking, RecurrenceType
from src.availability_utils import get_available_slots_for_day

@pytest.fixture
py_db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    yield db
    db.close()

def test_get_available_slots_basic(py_db_session):
    owner = Owner(name="Test Salon", slug="test-salon", email="test@salon.com", password_hash="hash")
    py_db_session.add(owner)
    py_db_session.commit()

    service = Service(owner_id=owner.id, name="Haircut", duration_minutes=30, price=20.0)
    py_db_session.add(service)
    py_db_session.commit()

    # Add recurring daily availability from 09:00 to 12:00
    avail = Availability(
        owner_id=owner.id,
        service_id=None,
        recurrence_type=RecurrenceType.DAILY,
        start_time=time(9, 0),
        end_time=time(12, 0)
    )
    py_db_session.add(avail)
    py_db_session.commit()

    target_date = date(2025, 6, 1)
    slots = get_available_slots_for_day(py_db_session, owner.id, service.id, target_date, service.duration_minutes)
    
    assert len(slots) == 6
    assert slots[0] == time(9, 0)
    assert slots[-1] == time(11, 30)
