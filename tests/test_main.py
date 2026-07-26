import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.database import Base, get_db
from src.main import app
from src.config import settings
import os

# Override database settings for testing
DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Override get_db dependency
def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

@pytest.fixture(name="client")
def client_fixture():
    # Create the database tables before each test
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as c:
        yield c
    # Drop the database tables after each test
    Base.metadata.drop_all(bind=engine)
    if os.path.exists("./test.db"):
        os.remove("./test.db")

@pytest.fixture(autouse=True)
def set_test_env_vars():
    # Set dummy environment variables for testing
    os.environ["SECRET_KEY"] = "super-secret-test-key"
    os.environ["SENDGRID_API_KEY"] = "SG.test"
    os.environ["TWILIO_ACCOUNT_SID"] = "ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    os.environ["TWILIO_AUTH_TOKEN"] = "your_auth_token"
    os.environ["TWILIO_WHATSAPP_NUMBER"] = "+1234567890"
    os.environ["DATABASE_URL"] = DATABASE_URL
    yield
    # Clean up environment variables after test
    del os.environ["SECRET_KEY"]
    del os.environ["SENDGRID_API_KEY"]
    del os.environ["TWILIO_ACCOUNT_SID"]
    del os.environ["TWILIO_AUTH_TOKEN"]
    del os.environ["TWILIO_WHATSAPP_NUMBER"]
    del os.environ["DATABASE_URL"]

def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_signup(client):
    response = client.post(
        "/signup",
        data={
            "name": "Test Owner",
            "email": "test@example.com",
            "password": "testpassword",
            "business_name": "Test Business",
            "slug": "test-business"
        },
        follow_redirects=False
    )
    assert response.status_code == 303 # Redirect to login
    assert response.headers["location"] == "/login"

def test_login_and_dashboard(client):
    # First, sign up
    client.post(
        "/signup",
        data={
            "name": "Test Owner",
            "email": "test@example.com",
            "password": "testpassword",
            "business_name": "Test Business",
            "slug": "test-business"
        },
    )

    # Then, log in
    response = client.post(
        "/token",
        data={"username": "test@example.com", "password": "testpassword"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        follow_redirects=False
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/dashboard"
    
    # Check if access_token cookie is set
    assert "access_token" in response.cookies

    # Access dashboard with the cookie
    dashboard_response = client.get("/dashboard")
    assert dashboard_response.status_code == 200
    assert "Test Owner" in dashboard_response.text
    assert "Test Business" in dashboard_response.text

def test_public_booking_page(client):
    # First, sign up an owner
    client.post(
        "/signup",
        data={
            "name": "Public Owner",
            "email": "public@example.com",
            "password": "publicpassword",
            "business_name": "Public Salon",
            "slug": "public-salon"
        },
    )
    
    # Get the public booking page
    response = client.get("/public-salon")
    assert response.status_code == 200
    assert "Public Salon" in response.text
    assert "Book an Appointment" in response.text

def test_submit_booking(client):
    # First, sign up an owner and update services
    client.post(
        "/signup",
        data={
            "name": "Booking Owner",
            "email": "booking@example.com",
            "password": "bookingpassword",
            "business_name": "Booking Clinic",
            "slug": "booking-clinic"
        },
    )
    
    # Log in to get the token
    login_response = client.post(
        "/token",
        data={"username": "booking@example.com", "password": "bookingpassword"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        follow_redirects=False
    )
    assert "access_token" in login_response.cookies
    access_token = login_response.cookies["access_token"]

    # Update owner profile with services
    profile_update_response = client.post(
        "/dashboard/profile",
        data={
            "name": "Booking Owner",
            "business_name": "Booking Clinic",
            "phone": "+1234567890",
            "services_json": '[{"id": 1, "name": "Consultation", "duration": 60}]',
            "availability_json": '{"monday": [{"start": "09:00", "end": "17:00"}]}'
        },
        cookies={"access_token": access_token},
        follow_redirects=False
    )
    assert profile_update_response.status_code == 303

    # Submit a booking on the public page
    booking_response = client.post(
        "/booking-clinic/book",
        data={
            "customer_name": "Jane Doe",
            "customer_email": "jane@example.com",
            "customer_phone": "+1987654321",
            "service_id": 1,
            "booking_time_str": "2025-01-01 10:00" # Future date
        },
    )
    assert booking_response.status_code == 200
    assert "Booking Confirmed!" in booking_response.text
    assert "Jane Doe" in booking_response.text
    assert "Consultation" in booking_response.text
    assert "Booking Clinic" in booking_response.text
