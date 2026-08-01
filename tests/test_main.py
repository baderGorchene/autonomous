import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.main import app
from src.database import Base, get_db
from src.config import settings
import json
from datetime import datetime, timedelta

# Override settings for testing
settings.DATABASE_URL = "sqlite:///./test.db" # Use a file for persistent test DB for now, or use :memory:
settings.TESTING = True
settings.SECRET_KEY = "super-secret-test-key" # A test secret key
settings.ALGORITHM = "HS256"

# Setup the Test Database
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db" # Using a file-based SQLite for easier debugging if needed
# SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:" # In-memory SQLite is usually preferred for speed

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(name="db_session")
def db_session_fixture():
    Base.metadata.create_all(bind=engine) # Create tables
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine) # Drop tables after test

@pytest.fixture(name="client")
def client_fixture(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            db_session.close() # This close is important for the fixture to clean up

    app.dependency_overrides[get_db] = override_get_db # Override src.database.get_db
    with TestClient(app) as client:
        yield client

def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "message": "BookSlot API is running!"}

def test_signup_page(client):
    response = client.get("/signup")
    assert response.status_code == 200
    assert "Sign Up for BookSlot" in response.text

def test_owner_signup_and_login(client):
    # Test Signup
    signup_data = {
        "name": "Test Owner",
        "email": "test@example.com",
        "password": "testpassword",
        "business_name": "Test Business",
        "slug": "test-business",
        "phone": "+1234567890"
    }
    response = client.post("/signup", data=signup_data, follow_redirects=False)
    assert response.status_code == 302 # Redirect to login
    assert response.headers["location"] == "/login"

    # Test Login
    login_data = {
        "username": "test@example.com",
        "password": "testpassword"
    }
    response = client.post("/login", data=login_data, follow_redirects=False)
    assert response.status_code == 302 # Redirect to dashboard
    assert response.headers["location"] == "/dashboard"
    assert "access_token" in response.cookies

    # Verify dashboard access with token
    access_token = response.cookies["access_token"]
    headers = {"Authorization": f"Bearer {access_token}"}
    response = client.get("/dashboard", headers=headers)
    assert response.status_code == 200
    assert "Welcome, Test Owner!" in response.text
    assert "Test Business" in response.text
    assert "bookslot.app/test-business" in response.text

def test_duplicate_email_signup(client):
    signup_data = {
        "name": "Test Owner",
        "email": "duplicate@example.com",
        "password": "testpassword",
        "business_name": "Test Business",
        "slug": "unique-slug"
    }
    client.post("/signup", data=signup_data) # First signup

    response = client.post("/signup", data=signup_data) # Duplicate signup
    assert response.status_code == 400
    assert "Email already registered" in response.text

def test_duplicate_slug_signup(client):
    signup_data_1 = {
        "name": "Owner One",
        "email": "owner1@example.com",
        "password": "testpassword",
        "business_name": "Business One",
        "slug": "duplicate-slug"
    }
    client.post("/signup", data=signup_data_1)

    signup_data_2 = {
        "name": "Owner Two",
        "email": "owner2@example.com",
        "password": "testpassword",
        "business_name": "Business Two",
        "slug": "duplicate-slug"
    }
    response = client.post("/signup", data=signup_data_2)
    assert response.status_code == 400
    assert "Business URL already taken" in response.text

def test_login_invalid_credentials(client):
    login_data = {
        "username": "nonexistent@example.com",
        "password": "wrongpassword"
    }
    response = client.post("/login", data=login_data)
    assert response.status_code == 401
    assert "Incorrect email or password" in response.text

def test_dashboard_unauthenticated(client):
    response = client.get("/dashboard")
    assert response.status_code == 401
    assert "Not authenticated" in response.text # FastAPI's default for missing token

def test_owner_profile_update(client):
    # Signup and Login
    signup_data = {
        "name": "Update Test Owner",
        "email": "update@example.com",
        "password": "testpassword",
        "business_name": "Update Business",
        "slug": "update-business",
        "phone": "+1112223333"
    }
    client.post("/signup", data=signup_data)
    login_data = {"username": "update@example.com", "password": "testpassword"}
    login_response = client.post("/login", data=login_data, follow_redirects=False)
    access_token = login_response.cookies["access_token"]
    headers = {"Authorization": f"Bearer {access_token}"}

    # Update profile
    updated_services = [
        {"name": "New Service", "duration": 30, "price": 50.0, "description": "A new test service"},
        {"name": "Old Service", "duration": 60, "price": 100.0, "description": ""}
    ]
    updated_availability = {
        "Monday": [{"start_time": "09:00", "end_time": "13:00"}],
        "Wednesday": [{"start_time": "14:00", "end_time": "18:00"}]
    }

    update_data = {
        "name": "Updated Test Owner",
        "business_name": "Updated Business Name",
        "phone": "+9998887777",
        "services": json.dumps(updated_services),
        "availability": json.dumps(updated_availability)
    }
    response = client.post("/dashboard/update_profile", data=update_data, headers=headers, follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/dashboard"

    # Verify updated profile on dashboard
    response = client.get("/dashboard", headers=headers)
    assert response.status_code == 200
    assert "Updated Test Owner" in response.text
    assert "Updated Business Name" in response.text
    assert "New Service" in response.text
    assert "9998887777" in response.text
    assert "09:00" in response.text # Check availability display
    assert "13:00" in response.text
    assert "14:00" in response.text
    assert "18:00" in response.text

def test_public_booking_page(client):
    # First, create an owner with services and availability
    signup_data = {
        "name": "Booking Owner",
        "email": "booking@example.com",
        "password": "testpassword",
        "business_name": "Booking Biz",
        "slug": "booking-biz",
        "phone": "+15551234567"
    }
    client.post("/signup", data=signup_data)

    login_data = {"username": "booking@example.com", "password": "testpassword"}
    login_response = client.post("/login", data=login_data, follow_redirects=False)
    access_token = login_response.cookies["access_token"]
    headers = {"Authorization": f"Bearer {access_token}"}

    services_data = [
        {"name": "Haircut", "duration": 30, "price": 25.0, "description": "A fresh cut"},
        {"name": "Coloring", "duration": 90, "price": 80.0, "description": "Full hair color"}
    ]
    availability_data = {
        "Monday": [{"start_time": "09:00", "end_time": "17:00"}],
        "Tuesday": [{"start_time": "10:00", "end_time": "18:00"}],
        "Friday": [{"start_time": "11:00", "end_time": "19:00"}]
    }
    update_data = {
        "name": "Booking Owner",
        "business_name": "Booking Biz",
        "phone": "+15551234567",
        "services": json.dumps(services_data),
        "availability": json.dumps(availability_data)
    }
    client.post("/dashboard/update_profile", data=update_data, headers=headers)

    # Now, access the public booking page
    response = client.get("/booking-biz")
    assert response.status_code == 200
    assert "Booking Biz" in response.text
    assert "Haircut" in response.text
    assert "Coloring" in response.text
    assert "Select a Service" in response.text

def test_submit_booking_success(client):
    # Ensure owner exists with availability
    signup_data = {
        "name": "Bookable Owner",
        "email": "bookable@example.com",
        "password": "testpassword",
        "business_name": "Bookable Service",
        "slug": "bookable-service",
        "phone": "+15559876543"
    }
    client.post("/signup", data=signup_data)

    login_data = {"username": "bookable@example.com", "password": "testpassword"}
    login_response = client.post("/login", data=login_data, follow_redirects=False)
    access_token = login_response.cookies["access_token"]
    headers = {"Authorization": f"Bearer {access_token}"}

    services_data = [
        {"name": "Consultation", "duration": 60, "price": 75.0, "description": "Initial talk"},
    ]
    # Make sure there's availability for a future Monday
    next_monday = (datetime.now() + timedelta(days=(0 - datetime.now().weekday() + 7) % 7)).strftime("%Y-%m-%d")
    availability_data = {
        "Monday": [{"start_time": "09:00", "end_time": "17:00"}],
    }
    update_data = {
        "name": "Bookable Owner",
        "business_name": "Bookable Service",
        "phone": "+15559876543",
        "services": json.dumps(services_data),
        "availability": json.dumps(availability_data)
    }
    client.post("/dashboard/update_profile", data=update_data, headers=headers)

    # Submit a booking
    booking_data = {
        "customer_name": "John Doe",
        "customer_email": "john.doe@example.com",
        "customer_phone": "+1234567890",
        "service_name": "Consultation",
        "booking_date": next_monday,
        "booking_time": "10:00"
    }
    response = client.post("/bookable-service/book", data=booking_data)
    assert response.status_code == 200
    assert "Booking Confirmed!" in response.text
    assert "John Doe" in response.text
    assert "Consultation" in response.text

    # Check dashboard for new booking
    response = client.get("/dashboard", headers=headers)
    assert response.status_code == 200
    assert "John Doe" in response.text
    assert "Consultation" in response.text
    assert next_monday in response.text
    assert "10:00" in response.text

def test_submit_booking_unavailable_slot(client):
    # Ensure owner exists with availability
    signup_data = {
        "name": "Slot Test Owner",
        "email": "slottest@example.com",
        "password": "testpassword",
        "business_name": "Slot Test Biz",
        "slug": "slot-test-biz",
        "phone": "+15550001111"
    }
    client.post("/signup", data=signup_data)

    login_data = {"username": "slottest@example.com", "password": "testpassword"}
    login_response = client.post("/login", data=login_data, follow_redirects=False)
    access_token = login_response.cookies["access_token"]
    headers = {"Authorization": f"Bearer {access_token}"}

    services_data = [
        {"name": "Quick Chat", "duration": 15, "price": 10.0, "description": "Quick discussion"},
    ]
    next_tuesday = (datetime.now() + timedelta(days=(1 - datetime.now().weekday() + 7) % 7)).strftime("%Y-%m-%d")
    availability_data = {
        "Tuesday": [{"start_time": "10:00", "end_time": "10:30"}], # Only a 30 min slot
    }
    update_data = {
        "name": "Slot Test Owner",
        "business_name": "Slot Test Biz",
        "phone": "+15550001111",
        "services": json.dumps(services_data),
        "availability": json.dumps(availability_data)
    }
    client.post("/dashboard/update_profile", data=update_data, headers=headers)

    # Try to book outside the slot (e.g., 11:00)
    booking_data_out_of_slot = {
        "customer_name": "Jane Doe",
        "customer_email": "jane.doe@example.com",
        "customer_phone": "+1234567890",
        "service_name": "Quick Chat",
        "booking_date": next_tuesday,
        "booking_time": "11:00"
    }
    response_out_of_slot = client.post("/slot-test-biz/book", data=booking_data_out_of_slot)
    assert response_out_of_slot.status_code == 400
    assert "The selected time slot is not available or the service duration exceeds the slot." in response_out_of_slot.text

    # Try to book a service that ends exactly at the slot end (10:15 booking for 15 min service in 10:00-10:30 slot)
    booking_data_valid_slot = {
        "customer_name": "Jane Doe",
        "customer_email": "jane.doe@example.com",
        "customer_phone": "+1234567890",
        "service_name": "Quick Chat",
        "booking_date": next_tuesday,
        "booking_time": "10:15"
    }
    response_valid_slot = client.post("/slot-test-biz/book", data=booking_data_valid_slot)
    assert response_valid_slot.status_code == 200 # This should pass
    assert "Booking Confirmed!" in response_valid_slot.text

    # Test booking in the past
    past_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    booking_data_past = {
        "customer_name": "Past Booker",
        "customer_email": "past@example.com",
        "customer_phone": "+1234567890",
        "service_name": "Quick Chat",
        "booking_date": past_date,
        "booking_time": "10:00"
    }
    response_past = client.post("/slot-test-biz/book", data=booking_data_past)
    assert response_past.status_code == 400
    assert "Cannot book in the past." in response_past.text

def test_language_toggle(client):
    response = client.get("/signup")
    assert "Sign Up for BookSlot" in response.text # Default English

    # Set locale to Arabic
    response = client.get("/set_locale/ar", follow_redirects=False)
    assert response.status_code == 302
    assert "location" in response.headers
    
    # Follow redirect to signup page with Arabic locale
    response = client.get(response.headers["location"])
    assert "سجل في BookSlot" in response.text
    
    # Set locale to French
    response = client.get("/set_locale/fr", follow_redirects=False)
    assert response.status_code == 302
    assert "location" in response.headers
    
    # Follow redirect to signup page with French locale
    response = client.get(response.headers["location"])
    assert "S'inscrire à BookSlot" in response.text
