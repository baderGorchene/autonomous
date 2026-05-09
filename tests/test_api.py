import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.main import app, get_db
from src.database import Base

SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

@pytest.fixture
def client():
    return TestClient(app)

def test_register_owner(client):
    payload = {
        "name": "John Doe",
        "email": "john@example.com",
        "business_name": "John's Barber",
        "slug": "john-barber",
        "services": [{"name": "Cut", "duration_minutes": 30, "price": 20.0}],
        "availability": [{"day_of_week": 0, "start_time": "09:00:00", "end_time": "17:00:00"}]
    }
    response = client.post("/register", json=payload)
    assert response.status_code == 200
    assert response.json()["slug"] == "john-barber"

def test_get_availability(client):
    # First register
    client.post("/register", json={
        "name": "Jane", "email": "jane@test.com", "business_name": "Clinic", "slug": "jane-clinic",
        "services": [{"name": "Consult", "duration_minutes": 30, "price": 50.0}],
        "availability": [{"day_of_week": 0, "start_time": "09:00:00", "end_time": "10:00:00"}]
    })
    # Request Monday (weekday 0) in 2023-10-02
    response = client.get("/jane-clinic/availability?date_str=2023-10-02&duration=30")
    assert response.status_code == 200
    slots = response.json()["slots"]
    assert len(slots) > 0
    assert "09:00" in slots[0]["start"]