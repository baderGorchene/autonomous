import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.main import app, get_db
from src.database import Base
from src.models import Owner
from datetime import datetime

SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(bind=engine)

Base.metadata.create_all(bind=engine)

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield

def test_conflict_check():
    # Register owner
    owner_data = {
        "name": "Test", "email": "t@t.com", "business_name": "Biz", "slug": "test-biz",
        "services": [{"name": "Haircut", "duration_minutes": 30}],
        "availability": [{"day_of_week": 0, "start_time": "09:00", "end_time": "17:00"}]
    }
    client.post("/register", json=owner_data)
    
    booking_time = "2023-10-02T10:00:00"
    booking = {"customer_name": "A", "customer_email": "a@a.com", "customer_phone": "123", "service_name": "Haircut", "datetime": booking_time}
    
    # First booking
    resp1 = client.post("/test-biz/book", json=booking)
    assert resp1.status_code == 200
    
    # Conflicting booking
    resp2 = client.post("/test-biz/book", json=booking)
    assert resp2.status_code == 400
    assert resp2.json()["detail"] == "Time slot already booked"

@pytest.mark.asyncio
async def test_notification_integration(httpx_mock):
    httpx_mock.add_response(url="https://api.sendgrid.com/v3/mail/send", status_code=202)
    
    from src.notifications import send_booking_notification
    await send_booking_notification("owner@test.com", "", {"customer": "John", "time": "2023-10-02T10:00:00"})
    
    assert httpx_mock.get_request().url.host == "api.sendgrid.com"
