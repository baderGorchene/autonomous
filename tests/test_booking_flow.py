import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.main import app
from src.database import Base
from src.models import Owner, Booking
from datetime import datetime

SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[lambda: None] = override_get_db # Simplified for example

@pytest.fixture(scope="function")
def db_session():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)

def test_submit_booking_flow(db_session):
    # Setup: Create an owner
    owner = Owner(name="Test User", email="test@test.com", business_name="Test Biz", slug="test-biz")
    db_session.add(owner)
    db_session.commit()
    
    client = TestClient(app)
    payload = {
        "owner_id": owner.id,
        "customer_name": "John Doe",
        "customer_email": "john@example.com",
        "customer_phone": "+123456789",
        "service": "Haircut",
        "datetime": "2023-12-01T10:00:00"
    }
    
    response = client.post("/book/submit", json=payload)
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    
    # Verify database record
    booking = db_session.query(Booking).filter(Booking.customer_name == "John Doe").first()
    assert booking is not None
    assert booking.service == "Haircut"
    assert booking.owner_id == owner.id