import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.database import Base
from src.models import Booking, Owner
from src.routes.booking import submit_booking
from datetime import datetime
from fastapi import BackgroundTasks, HTTPException

# Setup in-memory sqlite for testing
engine = create_engine('sqlite:///:memory:')
TestingSessionLocal = sessionmaker(bind=engine)
Base.metadata.create_all(bind=engine)

def get_test_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

@pytest.fixture
def db_session():
    return next(get_test_db())

@pytest.fixture
def setup_owner(db_session):
    owner = Owner(id=1, name='Test', email='test@test.com', slug='test')
    db_session.add(owner)
    db_session.commit()
    return owner

@pytest.mark.asyncio
async def test_booking_conflict_detection(db_session, setup_owner):
    booking_time = datetime(2023, 10, 10, 10, 0)
    data = {
        "owner_id": 1, "customer_name": "John", "customer_email": "john@ex.com",
        "customer_phone": "12345", "service": "Haircut", "datetime": booking_time
    }
    
    # First booking
    await submit_booking(type('obj', (object,), data)(**data), BackgroundTasks(), db_session)
    
    # Second booking at same time - should fail
    with pytest.raises(HTTPException) as exc:
        await submit_booking(type('obj', (object,), data)(**data), BackgroundTasks(), db_session)
    assert exc.value.status_code == 400
    assert "already booked" in exc.value.detail