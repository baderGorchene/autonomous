import pytest
from httpx import AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.database import Base, get_db
from src.main import app
from src.config import settings
import os
import json
from datetime import date, timedelta

# Override the database URL for testing to use an in-memory SQLite database
# This ensures tests are isolated and don't affect a real database
TEST_DATABASE_URL = "sqlite:///./test.db" # Use a file-based sqlite for persistence across test runs if needed, or :memory: for in-memory

# Ensure the test database file doesn't exist before starting tests if using file-based
if TEST_DATABASE_URL != "sqlite:///:memory:" and os.path.exists(TEST_DATABASE_URL.replace("sqlite:///","")):
    os.remove(TEST_DATABASE_URL.replace("sqlite:///",""))

engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Dependency override for testing
def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

@pytest.fixture(name="test_db")
def test_db_fixture():
    # Create tables
    Base.metadata.create_all(bind=engine)
    yield
    # Drop tables after tests
    Base.metadata.drop_all(bind=engine)

@pytest.fixture(name="client")
async def client_fixture(test_db):
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client

# --- Helper functions for common operations ---
async def signup_owner(client: AsyncClient, email: str, password: str, slug: str):
    response = await client.post(
        "/signup",
        json={
            "name": "Test Owner",
            "email": email,
            "password": password,
            "business_name": "Test Business",
            "slug": slug,
            "phone": "+1234567890"
        }
    )
    assert response.status_code == 200
    return response.json()["access_token"]

async def login_owner(client: AsyncClient, email: str, password: str):
    response = await client.post(
        "/token",
        data={"username": email, "password": password}
    )
    assert response.status_code == 200
    return response.json()["access_token"]

# --- Tests ---

@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

@pytest.mark.asyncio
async def test_owner_signup_and_login(client: AsyncClient):
    # Signup
    email = "testowner@example.com"
    password = "testpassword"
    slug = "test-business-slug"
    access_token = await signup_owner(client, email, password, slug)
    assert access_token is not None

    # Login with correct credentials
    token = await login_owner(client, email, password)
    assert token is not None

    # Login with incorrect password
    response = await client.post(
        "/token",
        data={"username": email, "password": "wrongpassword"}
    )
    assert response.status_code == 401

    # Login with unregistered email
    response = await client.post(
        "/token",
        data={"username": "nonexistent@example.com", "password": "anypassword"}
    )
    assert response.status_code == 401

@pytest.mark.asyncio
async def test_duplicate_email_signup(client: AsyncClient):
    email = "duplicate@example.com"
    password = "testpassword"
    slug = "duplicate-slug"
    await signup_owner(client, email, password, slug)

    response = await client.post(
        "/signup",
        json={
            "name": "Another Test Owner",
            "email": email, # Duplicate email
            "password": password,
            "business_name": "Another Business",
            "slug": "another-slug",
            "phone": "+1987654321"
        }
    )
    assert response.status_code == 400
    assert "Email already registered" in response.json()["detail"]

@pytest.mark.asyncio
async def test_duplicate_slug_signup(client: AsyncClient):
    email = "slugtest@example.com"
    password = "testpassword"
    slug = "duplicate-slug-test"
    await signup_owner(client, email, password, slug)

    response = await client.post(
        "/signup",
        json={
            "name": "Another Test Owner",
            "email": "anotheremail@example.com",
            "password": password,
            "business_name": "Another Business",
            "slug": slug, # Duplicate slug
            "phone": "+1987654321"
        }
    )
    assert response.status_code == 400
    assert "Business slug already taken" in response.json()["detail"]

@pytest.mark.asyncio
async def test_dashboard_access(client: AsyncClient):
    token = await signup_owner(client, "dashboard@example.com", "password", "dashboard-slug")

    # Access dashboard with token
    response = await client.get(
        "/dashboard",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    assert "Welcome, Test Owner!" in response.text # Check for content in rendered template

    # Access dashboard without token
    response = await client.get("/dashboard")
    assert response.status_code == 401 # Should redirect or return unauthorized

@pytest.mark.asyncio
async def test_profile_update(client: AsyncClient):
    email = "profile@example.com"
    password = "password"
    slug = "profile-slug"
    token = await signup_owner(client, email, password, slug)

    updated_profile_data = {
        "name": "Updated Name",
        "business_name": "Updated Business",
        "phone": "+1122334455",
        "services": [
            {"name": "Haircut", "duration": 30, "price": 25.0, "description": "Standard haircut"},
            {"name": "Shave", "duration": 15, "price": 10.0}
        ],
        "availability": {
            "Monday": [{"start_time": "09:00", "end_time": "17:00"}],
            "Wednesday": [{"start_time": "10:00", "end_time": "18:00"}]
        }
    }

    response = await client.post(
        "/profile/update",
        json=updated_profile_data,
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Updated Name"
    assert response.json()["business_name"] == "Updated Business"
    assert response.json()["phone"] == "+1122334455"
    
    # Verify services and availability are updated in the database by fetching dashboard
    dashboard_response = await client.get(
        "/dashboard",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert "Haircut" in dashboard_response.text
    assert "09:00" in dashboard_response.text

@pytest.mark.asyncio
async def test_public_booking_page(client: AsyncClient):
    email = "publicbooker@example.com"
    password = "password"
    slug = "bookslot-test-owner"
    token = await signup_owner(client, email, password, slug)

    # Update profile with services and availability for booking
    updated_profile_data = {
        "name": "BookSlot Test Owner",
        "business_name": "BookSlot Salon",
        "phone": "+1122334455",
        "services": [
            {"name": "Basic Haircut", "duration": 30, "price": 50.0},
            {"name": "Coloring", "duration": 120, "price": 150.0}
        ],
        "availability": {
            (date.today() + timedelta(days=1)).strftime("%A"): [{"start_time": "09:00", "end_time": "17:00"}]
        }
    }
    await client.post("/profile/update", json=updated_profile_data, headers={"Authorization": f"Bearer {token}"})

    response = await client.get(f"/bookslot.app/{slug}")
    assert response.status_code == 200
    assert "BookSlot Salon" in response.text
    assert "Basic Haircut" in response.text
    assert "Coloring" in response.text
    assert (date.today() + timedelta(days=1)).strftime("%A") in response.text # Check for next day's availability

@pytest.mark.asyncio
async def test_booking_submission(client: AsyncClient):
    email = "bookingowner@example.com"
    password = "password"
    slug = "booking-test-owner"
    token = await signup_owner(client, email, password, slug)

    # Update profile with services and availability for booking
    booking_date = date.today() + timedelta(days=2) # Book for 2 days from now
    updated_profile_data = {
        "name": "Booking Test Owner",
        "business_name": "Booking Clinic",
        "phone": "+1234567890", # Ensure owner has phone for WhatsApp test
        "services": [
            {"name": "Consultation", "duration": 60, "price": 100.0}
        ],
        "availability": {
            booking_date.strftime("%A"): [{"start_time": "09:00", "end_time": "17:00"}]
        }
    }
    await client.post("/profile/update", json=updated_profile_data, headers={"Authorization": f"Bearer {token}"})

    # Submit a booking
    response = await client.post(
        f"/bookslot.app/{slug}/submit",
        data={
            "customer_name": "John Doe",
            "customer_email": "john.doe@example.com",
            "customer_phone": "+1987654321",
            "service_name": "Consultation",
            "booking_date": booking_date.isoformat(),
            "booking_time": "10:00"
        },
        follow_redirects=False # Do not follow redirect to check status code
    )
    assert response.status_code == 303 # Should redirect on success
    assert "Booking confirmed!" in response.headers["location"]

    # Verify booking appears in dashboard
    dashboard_response = await client.get(
        "/dashboard",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert "John Doe" in dashboard_response.text
    assert "Consultation" in dashboard_response.text
    assert "10:00" in dashboard_response.text

@pytest.mark.asyncio
async def test_internationalization_dashboard(client: AsyncClient):
    token = await signup_owner(client, "i18n@example.com", "password", "i18n-slug")

    # Test Arabic
    response_ar = await client.get(
        "/dashboard?lang=ar",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response_ar.status_code == 200
    assert "لوحة التحكم" in response_ar.text # Arabic for Dashboard
    assert "مرحباً بك،" in response_ar.text # Arabic for Welcome,

    # Test French
    response_fr = await client.get(
        "/dashboard?lang=fr",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response_fr.status_code == 200
    assert "Tableau de bord" in response_fr.text # French for Dashboard
    assert "Bienvenue," in response_fr.text # French for Welcome,

    # Test English (default)
    response_en = await client.get(
        "/dashboard",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response_en.status_code == 200
    assert "Dashboard" in response_en.text
    assert "Welcome," in response_en.text

@pytest.mark.asyncio
async def test_internationalization_booking_page(client: AsyncClient):
    email = "i18nbooker@example.com"
    password = "password"
    slug = "i18n-book-page"
    token = await signup_owner(client, email, password, slug)
    
    # Update profile with services for booking page
    updated_profile_data = {
        "name": "I18n Booker",
        "business_name": "I18n Service",
        "phone": "+1122334455",
        "services": [
            {"name": "Test Service", "duration": 30, "price": 50.0}
        ],
        "availability": {}
    }
    await client.post("/profile/update", json=updated_profile_data, headers={"Authorization": f"Bearer {token}"})

    # Test Arabic
    response_ar = await client.get(f"/bookslot.app/{slug}?lang=ar")
    assert response_ar.status_code == 200
    assert "احجز الآن" in response_ar.text # Arabic for Book Now
    assert "1. اختر خدمة" in response_ar.text # Arabic for 1. Select a Service

    # Test French
    response_fr = await client.get(f"/bookslot.app/{slug}?lang=fr")
    assert response_fr.status_code == 200
    assert "Réserver maintenant" in response_fr.text # French for Book Now
    assert "1. Sélectionnez un service" in response_fr.text # French for 1. Select a Service

@pytest.mark.asyncio
async def test_error_handling_booking_submission(client: AsyncClient):
    email = "errorowner@example.com"
    password = "password"
    slug = "error-test-owner"
    token = await signup_owner(client, email, password, slug)

    # Update profile with services and availability
    booking_date = date.today() + timedelta(days=1)
    updated_profile_data = {
        "name": "Error Test Owner",
        "business_name": "Error Clinic",
        "phone": "+1234567890",
        "services": [
            {"name": "Consultation", "duration": 60, "price": 100.0}
        ],
        "availability": {
            booking_date.strftime("%A"): [{"start_time": "09:00", "end_time": "17:00"}]
        }
    }
    await client.post("/profile/update", json=updated_profile_data, headers={"Authorization": f"Bearer {token}"})

    # Missing required field (customer_name)
    response = await client.post(
        f"/bookslot.app/{slug}/submit",
        data={
            "customer_email": "invalid@example.com",
            "service_name": "Consultation",
            "booking_date": booking_date.isoformat(),
            "booking_time": "10:00"
        },
        follow_redirects=False
    )
    assert response.status_code == 422 # FastAPI Pydantic validation error for missing form field
    # The actual HTML form submission might result in 400 with a custom message,
    # but direct POST to endpoint will be 422 for Pydantic validation

    # Invalid email format
    response = await client.post(
        f"/bookslot.app/{slug}/submit",
        data={
            "customer_name": "Invalid Email",
            "customer_email": "invalid-email", # Invalid email
            "service_name": "Consultation",
            "booking_date": booking_date.isoformat(),
            "booking_time": "10:00"
        },
        follow_redirects=False
    )
    assert response.status_code == 422

@pytest.mark.asyncio
async def test_error_handling_profile_update(client: AsyncClient):
    email = "updateerror@example.com"
    password = "password"
    slug = "update-error-slug"
    token = await signup_owner(client, email, password, slug)

    # Invalid services format (not a list)
    invalid_services_data = {
        "name": "Test Name",
        "business_name": "Test Business",
        "phone": "+1234567890",
        "services": "not a list", # Invalid
        "availability": {}
    }
    response = await client.post(
        "/profile/update",
        json=invalid_services_data,
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 422 # Pydantic validation error

    # Invalid service item format (missing name)
    invalid_service_item_data = {
        "name": "Test Name",
        "business_name": "Test Business",
        "phone": "+1234567890",
        "services": [{"duration": 30, "price": 25.0}], # Missing name
        "availability": {}
    }
    response = await client.post(
        "/profile/update",
        json=invalid_service_item_data,
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 422
    
    # Invalid availability format (not a dict)
    invalid_availability_data = {
        "name": "Test Name",
        "business_name": "Test Business",
        "phone": "+1234567890",
        "services": [],
        "availability": "not a dict" # Invalid
    }
    response = await client.post(
        "/profile/update",
        json=invalid_availability_data,
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 422

    # Invalid time format in availability
    invalid_time_format_data = {
        "name": "Test Name",
        "business_name": "Test Business",
        "phone": "+1234567890",
        "services": [],
        "availability": {
            "Monday": [{"start_time": "09-00", "end_time": "17:00"}] # Invalid time format
        }
    }
    response = await client.post(
        "/profile/update",
        json=invalid_time_format_data,
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 400 # Custom validation in main.py for time format
    assert "Invalid time format" in response.json()["detail"]
