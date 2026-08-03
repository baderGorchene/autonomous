import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.main import app
from src.database import Base, get_db
from src.config import settings
from src.models import Owner # Import Owner model
from src import security
import json

# Override database settings for testing
settings.DATABASE_URL = "sqlite:///./test.db" # Use a separate test database
settings.TESTING = True

# Setup test database
connect_args = {"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {}
engine = create_engine(settings.DATABASE_URL, **connect_args)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(name="db_session")
def db_session_fixture():
    Base.metadata.drop_all(bind=engine) # Clear tables for a clean test run
    Base.metadata.create_all(bind=engine) # Create tables
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        # Base.metadata.drop_all(bind=engine) # Clean up after tests - often handled by the test runner or a global teardown

@pytest.fixture(name="client")
def client_fixture(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            # db_session.close() # Session is closed by the fixture already
            pass
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()

# Fixture to create a test owner
@pytest.fixture(name="test_owner")
def test_owner_fixture(db_session):
    hashed_password = security.get_password_hash("testpassword")
    owner_data = {
        "name": "Test Owner",
        "email": "test@example.com",
        "hashed_password": hashed_password,
        "business_name": "Test Salon",
        "slug": "test-salon",
        "services_json": json.dumps([{"name": "Haircut", "description": "Mens haircut", "duration": 30, "price": 25.0, "currency": "USD"}]),
        "availability_json": json.dumps({"Monday": [{"start_time": "09:00", "end_time": "17:00"}]}),
        "phone": "+15551234567"
    }
    owner = Owner(**owner_data)
    db_session.add(owner)
    db_session.commit()
    db_session.refresh(owner)
    return owner

def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_root_page_english(client):
    response = client.get("/?lang=en")
    assert response.status_code == 200
    assert "Welcome to BookSlot!" in response.text
    assert "English" in response.text
    assert "Arabic" in response.text
    assert "French" in response.text

def test_root_page_arabic(client):
    response = client.get("/?lang=ar")
    assert response.status_code == 200
    assert "مرحباً بك في بوك سلوت!" in response.text # Assuming this is the Arabic translation
    assert "الإنجليزية" in response.text
    assert "العربية" in response.text
    assert "الفرنسية" in response.text

def test_root_page_french(client):
    response = client.get("/?lang=fr")
    assert response.status_code == 200
    assert "Bienvenue sur BookSlot !" in response.text # Assuming this is the French translation
    assert "Anglais" in response.text
    assert "Arabe" in response.text
    assert "Français" in response.text

def test_create_owner(client):
    response = client.post(
        "/owners/",
        json={
            "name": "New Owner",
            "email": "new@example.com",
            "password": "securepassword",
            "business_name": "New Business",
            "slug": "new-business-slug",
            "phone": "+1234567890"
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "new@example.com"
    assert "id" in data

def test_create_owner_duplicate_email(client, test_owner):
    response = client.post(
        "/owners/",
        json={
            "name": "Another Owner",
            "email": "test@example.com", # Duplicate email
            "password": "securepassword",
            "business_name": "Another Business",
            "slug": "another-business-slug",
            "phone": "+1234567891"
        },
    )
    assert response.status_code == 400
    assert response.json() == {"detail": "Email already registered"}

def test_get_booking_page(client, test_owner):
    response = client.get(f"/{test_owner.slug}")
    assert response.status_code == 200
    assert test_owner.business_name in response.text
    assert "Haircut" in response.text

def test_create_booking(client, test_owner):
    booking_data = {
        "customer_name": "Jane Doe",
        "customer_email": "jane@example.com",
        "customer_phone": "+1234567890",
        "service_name": "Haircut",
        "booking_date": "2023-12-25",
        "booking_time": "10:00"
    }
    response = client.post(f"/{test_owner.slug}/book", json=booking_data)
    assert response.status_code == 200
    assert "Booking Confirmed!" in response.text
    assert "Jane Doe" in response.text
    assert "Haircut" in response.text
    assert "2023-12-25" in response.text
    assert "10:00" in response.text

def test_create_booking_missing_data(client, test_owner):
    booking_data = {
        "customer_name": "Jane Doe",
        "customer_email": "jane@example.com",
        "service_name": "Haircut",
        "booking_date": "2023-12-25" # Missing booking_time
    }
    response = client.post(f"/{test_owner.slug}/book", json=booking_data)
    assert response.status_code == 422 # Pydantic validation error

# Test currency formatting filter
def test_currency_filter_english(client, test_owner):
    response = client.get(f"/{test_owner.slug}?lang=en")
    assert "$25.00" in response.text

def test_currency_filter_arabic(client, test_owner):
    response = client.get(f"/{test_owner.slug}?lang=ar")
    assert "25.00 ر.س" in response.text # Assuming SAR for Arabic example

def test_currency_filter_french(client, test_owner):
    response = client.get(f"/{test_owner.slug}?lang=fr")
    assert "25,00 €" in response.text # Assuming EUR for French example