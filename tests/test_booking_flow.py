import pytest
import httpx
from fastapi.testclient import TestClient
from src.main import app
from src.database import Base, engine
from src import models

@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

client = TestClient(app)

def test_submit_booking_flow(monkeypatch):
    # Mock notification sending to avoid real network calls
    async def mock_send(*args, **kwargs):
        return True
    
    monkeypatch.setattr("src.notifications.send_booking_notification", mock_send)

    # Setup an owner
    owner_data = {"name": "Test", "email": "t@t.com", "business_name": "Shop", "slug": "test-shop"}
    client.post("/auth/signup", data=owner_data)
    
    # Submit booking
    booking_payload = {
        "owner_id": 1,
        "customer_name": "John Doe",
        "customer_email": "john@example.com",
        "customer_phone": "123456789",
        "service": "Haircut",
        "datetime": "2023-12-01T10:00:00"
    }
    
    response = client.post("/book/submit", json=booking_payload)
    assert response.status_code == 200
    assert response.json()["status"] == "success"