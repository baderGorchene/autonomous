import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.database import Base, get_db
from src.main import app
from src.config import settings
import os
import json
import datetime

# Setup a test database
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
# Override the DATABASE_URL for testing
settings.DATABASE_URL = SQLALCHEMY_DATABASE_URL
settings.TESTING = True # Set testing flag

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(name="session")
def session_fixture():
    Base.metadata.drop_all(bind=engine) # Start fresh for each test
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

@pytest.fixture(name="client")
def client_fixture(session: TestingSessionLocal):
    def override_get_db():
        yield session
    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear() # Clean up overrides

# --- Helper functions for tests ---
def get_owner_token(client: TestClient, email, password):
    response = client.post(
        "/token",
        data={"username": email, "password": password}
    )
    assert response.status_code == 200
    return response.json()["access_token"]

# --- Tests ---

def test_health_check(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_signup_owner(client: TestClient):
    # Test successful signup
    response = client.post(
        "/signup",
        data={
            "name": "Test Owner",
            "email": "test@example.com",
            "password": "testpassword",
            "business_name": "Test Business",
            "slug": "test-business",
            "phone": "+1234567890"
        },
        follow_redirects=False # Don't follow redirect to /login
    )
    assert response.status_code == 303 # Should redirect to login
    assert response.headers["location"] == "/login"

    # Test duplicate email signup
    response = client.post(
        "/signup",
        data={
            "name": "Another Owner",
            "email": "test@example.com", # Duplicate email
            "password": "anotherpassword",
            "business_name": "Another Business",
            "slug": "another-business",
            "phone": "+1987654321"
        }
    )
    assert response.status_code == 200 # Renders signup page with error
    assert "Email already registered" in response.text

    # Test duplicate slug signup
    response = client.post(
        "/signup",
        data={
            "name": "Yet Another Owner",
            "email": "yet@example.com",
            "password": "yetanotherpassword",
            "business_name": "Yet Another Business",
            "slug": "test-business", # Duplicate slug
            "phone": "+1112223333"
        }
    )
    assert response.status_code == 200 # Renders signup page with error
    assert "Business URL already taken" in response.text

def test_login_owner(client: TestClient):
    # First, sign up an owner
    client.post(
        "/signup",
        data={
            "name": "Login Test",
            "email": "login@example.com",
            "password": "loginpassword",
            "business_name": "Login Business",
            "slug": "login-business",
            "phone": "+1234567890"
        },
        follow_redirects=False
    )

    # Test successful login via form
    response = client.post(
        "/login",
        data={"email": "login@example.com", "password": "loginpassword"},
        follow_redirects=False
    )
    assert response.status_code == 303 # Should redirect to dashboard
    assert response.headers["location"] == "/dashboard"
    assert "access_token" in response.cookies

    # Test invalid credentials
    response = client.post(
        "/login",
        data={"email": "login@example.com", "password": "wrongpassword"}
    )
    assert response.status_code == 200 # Renders login page with error
    assert "Incorrect email or password" in response.text

def test_dashboard_access(client: TestClient):
    # First, sign up and log in an owner
    client.post(
        "/signup",
        data={
            "name": "Dashboard Owner",
            "email": "dashboard@example.com",
            "password": "dashboardpassword",
            "business_name": "Dashboard Business",
            "slug": "dashboard-business",
            "phone": "+1234567890"
        },
        follow_redirects=False
    )
    login_response = client.post(
        "/login",
        data={"email": "dashboard@example.com", "password": "dashboardpassword"},
        follow_redirects=False
    )
    access_token = login_response.cookies["access_token"]

    # Test authenticated access
    response = client.get(
        "/dashboard",
        cookies={"access_token": access_token}
    )
    assert response.status_code == 200
    assert "Welcome, Dashboard Owner!" in response.text
    assert "Your Booking Page Link: <a href=\"/bookslot.app/dashboard-business\"" in response.text

    # Test unauthenticated access (no token)
    response = client.get("/dashboard")
    assert response.status_code == 401 # Should be unauthorized due to Depends(get_current_owner)

def test_update_owner_profile(client: TestClient):
    # Sign up and log in
    client.post("/signup", data={"name": "Updater", "email": "updater@example.com", "password": "pass", "business_name": "OldBiz", "slug": "updater", "phone": ""}, follow_redirects=False)
    login_response = client.post("/login", data={"email": "updater@example.com", "password": "pass"}, follow_redirects=False)
    access_token = login_response.cookies["access_token"]

    updated_services = json.dumps([{"name": "New Service", "description": "Desc", "duration_minutes": 60, "price": 100.0}])
    updated_availability = json.dumps({
        "monday": {"is_available": True, "slots": [{"start_time": "09:00", "end_time": "17:00"}]},
        "tuesday": {"is_available": False, "slots": []}
    })

    response = client.post(
        "/dashboard/profile",
        data={
            "name": "Updated Updater",
            "business_name": "New Business Name",
            "phone": "+9876543210",
            "services_data": updated_services,
            "availability_data": updated_availability
        },
        cookies={"access_token": access_token}
    )
    assert response.status_code == 200
    assert "Profile updated successfully!" in response.text
    assert "Updated Updater" in response.text
    assert "New Business Name" in response.text
    assert "+9876543210" in response.text
    assert "New Service" in response.text
    assert "09:00" in response.text # Check for availability update

    # Test with invalid JSON
    response = client.post(
        "/dashboard/profile",
        data={
            "name": "Updater",
            "business_name": "OldBiz",
            "phone": "",
            "services_data": "invalid json",
            "availability_data": "{}"
        },
        cookies={"access_token": access_token}
    )
    assert response.status_code == 200
    assert "Invalid JSON format for services or availability." in response.text

def test_public_booking_page(client: TestClient):
    # Sign up an owner
    client.post(
        "/signup",
        data={
            "name": "Booker",
            "email": "booker@example.com",
            "password": "pass",
            "business_name": "Booker's Spa",
            "slug": "bookers-spa",
            "phone": "+1112223333"
        },
        follow_redirects=False
    )
    # Update services and availability for the owner
    login_response = client.post("/login", data={"email": "booker@example.com", "password": "pass"}, follow_redirects=False)
    access_token = login_response.cookies["access_token"]
    
    services_data = json.dumps([{"name": "Massage", "description": "Relaxing", "duration_minutes": 60, "price": 80.0}])
    availability_data = json.dumps({
        "monday": {"is_available": True, "slots": [{"start_time": "09:00", "end_time": "17:00"}]},
        "tuesday": {"is_available": False, "slots": []},
        "wednesday": {"is_available": True, "slots": [{"start_time": "10:00", "end_time": "12:00"}]}
    })
    client.post(
        "/dashboard/profile",
        data={
            "name": "Booker", "business_name": "Booker's Spa", "phone": "+1112223333",
            "services_data": services_data, "availability_data": availability_data
        },
        cookies={"access_token": access_token}
    )

    # Test accessing public booking page
    response = client.get("/bookslot.app/bookers-spa")
    assert response.status_code == 200
    assert "Booker's Spa" in response.text
    assert "Massage" in response.text # Check if service is displayed

    # Test non-existent slug
    response = client.get("/bookslot.app/non-existent-slug")
    assert response.status_code == 404
    assert "Booking page not found" in response.json()["detail"]

def test_submit_booking(client: TestClient):
    # Sign up an owner (same as above for setup)
    client.post(
        "/signup",
        data={
            "name": "Booker",
            "email": "booker_submit@example.com",
            "password": "pass",
            "business_name": "Booker's Spa",
            "slug": "bookers-spa-submit",
            "phone": "+1112223333"
        },
        follow_redirects=False
    )
    login_response = client.post("/login", data={"email": "booker_submit@example.com", "password": "pass"}, follow_redirects=False)
    access_token = login_response.cookies["access_token"]
    
    services_data = json.dumps([{"name": "Massage", "description": "Relaxing", "duration_minutes": 60, "price": 80.0}])
    # Ensure availability for a future date
    tomorrow = (datetime.date.today() + datetime.timedelta(days=1)).strftime("%A").lower()
    availability_data = json.dumps({
        tomorrow: {"is_available": True, "slots": [{"start_time": "10:00", "end_time": "12:00"}]}
    })
    client.post(
        "/dashboard/profile",
        data={
            "name": "Booker", "business_name": "Booker's Spa", "phone": "+1112223333",
            "services_data": services_data, "availability_data": availability_data
        },
        cookies={"access_token": access_token}
    )

    booking_date = (datetime.date.today() + datetime.timedelta(days=1)).strftime("%Y-%m-%d")

    # Test successful booking submission
    response = client.post(
        "/bookslot.app/bookers-spa-submit/book",
        data={
            "customer_name": "Jane Doe",
            "customer_email": "jane@example.com",
            "customer_phone": "+9988776655",
            "service_name": "Massage",
            "booking_date": booking_date,
            "booking_time": "10:00 AM"
        }
    )
    assert response.status_code == 200
    assert "Booking Confirmed!" in response.text
    assert "Jane Doe" in response.text
    assert "Massage" in response.text
    assert booking_date in response.text
    assert "10:00 AM" in response.text

    # Test booking with invalid date format
    response = client.post(
        "/bookslot.app/bookers-spa-submit/book",
        data={
            "customer_name": "Invalid Date",
            "customer_email": "invalid@example.com",
            "customer_phone": "+9988776655",
            "service_name": "Massage",
            "booking_date": "2023/10/27", # Invalid format
            "booking_time": "10:00 AM"
        }
    )
    assert response.status_code == 200 # Renders booking page with error
    assert "Invalid date or time format." in response.text

def test_language_toggle(client: TestClient):
    # Test setting language to Arabic on root
    response = client.get("/set_lang/ar", follow_redirects=False)
    assert response.status_code == 303
    assert response.cookies["lang"] == "ar"

    # Access signup page with Arabic cookie
    response = client.get("/signup", cookies={"lang": "ar"})
    assert response.status_code == 200
    assert "التسجيل" in response.text # Check for Arabic translation of "Sign Up"

    # Test setting language to French on root
    response = client.get("/set_lang/fr", follow_redirects=False)
    assert response.status_code == 303
    assert response.cookies["lang"] == "fr"

    # Access signup page with French cookie
    response = client.get("/signup", cookies={"lang": "fr"})
    assert response.status_code == 200
    assert "S'inscrire" in response.text # Check for French translation of "Sign Up"

    # Test language toggle on dashboard
    client.post(
        "/signup",
        data={
            "name": "Lang Tester",
            "email": "lang@example.com",
            "password": "langpass",
            "business_name": "Lang Business",
            "slug": "lang-business",
            "phone": ""
        },
        follow_redirects=False
    )
    login_response = client.post("/login", data={"email": "lang@example.com", "password": "langpass"}, follow_redirects=False)
    access_token = login_response.cookies["access_token"]

    response = client.get("/dashboard", cookies={"access_token": access_token, "lang": "fr"})
    assert response.status_code == 200
    assert "Tableau de bord" in response.text # Check French translation

    response = client.get("/dashboard", cookies={"access_token": access_token, "lang": "ar"})
    assert response.status_code == 200
    assert "لوحة التحكم" in response.text # Check Arabic translation
