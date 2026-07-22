from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.main import app, get_db
from src.database import Base
from src import models, schemas, security
from datetime import datetime, timedelta
import pytest

# Setup an in-memory SQLite database for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Override the get_db dependency to use the test database
def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

# Create a test client
client = TestClient(app)

@pytest.fixture(name="db_session")
def db_session_fixture():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        # Create a test owner for the booking page
        hashed_password = security.get_password_hash("testpassword")
        test_owner = models.Owner(
            name="Test Owner",
            email="test@example.com",
            hashed_password=hashed_password,
            business_name="Test Business",
            slug="test-business",
            services_json=[{"name": "Consultation", "duration": 30}],
            availability_json={
                "monday": [{"start": "09:00", "end": "17:00"}],
                "tuesday": [{"start": "09:00", "end": "17:00"}],
                "wednesday": [{"start": "09:00", "end": "17:00"}],
                "thursday": [{"start": "09:00", "end": "17:00"}],
                "friday": [{"start": "09:00", "end": "17:00"}]
            },
            phone="1234567890"
        )
        db.add(test_owner)
        db.commit()
        db.refresh(test_owner)
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)

def test_booking_page_english_translation(db_session):
    response = client.get("/book/test-business?lang=en")
    assert response.status_code == 200
    assert "Book an Appointment" in response.text
    assert "Select a Service" in response.text
    assert "English" in response.text
    assert "Arabic" in response.text
    assert "French" in response.text

def test_booking_page_arabic_translation(db_session):
    response = client.get("/book/test-business?lang=ar")
    assert response.status_code == 200
    assert "احجز موعدا" in response.text
    assert "اختر خدمة" in response.text
    assert "الإنجليزية" in response.text
    assert "العربية" in response.text
    assert "الفرنسية" in response.text

def test_booking_page_french_translation(db_session):
    response = client.get("/book/test-business?lang=fr")
    assert response.status_code == 200
    assert "Prendre un rendez-vous" in response.text
    assert "Sélectionner un service" in response.text
    assert "Anglais" in response.text
    assert "Arabe" in response.text
    assert "Français" in response.text
