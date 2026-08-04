import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.main import app, get_db, templates
from src.database import Base, get_db as get_db_override, create_tables, drop_tables # Import drop_tables
from src import models, security
from src.config import settings
import datetime
import json
from unittest.mock import patch, MagicMock

# Override settings for testing
settings.TESTING = True
settings.DATABASE_URL = "sqlite:///./test_sql_app.db" # Use a separate DB for tests

# Setup test database
engine = create_engine(settings.DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="module")
def test_db():
    # Drop and create tables for a clean slate
    drop_tables()
    create_tables()
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        drop_tables() # Clean up after tests

@pytest.fixture(scope="function")
def client(test_db):
    def override_get_db():
        try:
            yield test_db
        finally:
            test_db.rollback() # Rollback changes after each test
            # Clear data for function-scoped fixture
            for table in reversed(Base.metadata.sorted_tables):
                test_db.execute(table.delete())
            test_db.commit()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides = {} # Clear overrides

# Helper function to create a test owner
def create_test_owner(db, email="test@example.com", password="password", slug="test-business"):
    owner_data = models.Owner(
        name="Test Owner",
        email=email,
        hashed_password=security.get_password_hash(password),
        business_name="Test Business",
        slug=slug,
        services_json=json.dumps([{"name": "Service 1", "duration": 60, "price": 50.0}]),
        availability_json=json.dumps({"Monday": [{"start_time": "09:00", "end_time": "17:00"}]}),
        phone="+1234567890"
    )
    db.add(owner_data)
    db.commit()
    db.refresh(owner_data)
    return owner_data

# Helper function to get an access token
def get_access_token(client, email, password):
    response = client.post("/token", data={"username": email, "password": password})
    return response.cookies.get("access_token")


# --- Test Cases ---

def test_root_redirects_to_login(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Login to BookSlot" in response.text

def test_register_page(client):
    response = client.get("/register")
    assert response.status_code == 200
    assert "Register for BookSlot" in response.text

def test_register_owner_success(client, test_db):
    response = client.post("/register", data={
        "name": "New Owner",
        "email": "new@example.com",
        "password": "newpassword",
        "business_name": "New Business",
        "slug": "new-business-slug",
        "phone": "+1122334455"
    })
    assert response.status_code == 200
    assert "Registration successful! Please log in." in response.text
    owner = test_db.query(models.Owner).filter(models.Owner.email == "new@example.com").first()
    assert owner is not None
    assert owner.business_name == "New Business"

def test_register_owner_duplicate_email(client, test_db):
    create_test_owner(test_db, email="existing@example.com", slug="existing-slug")
    response = client.post("/register", data={
        "name": "Duplicate Owner",
        "email": "existing@example.com",
        "password": "password",
        "business_name": "Another Business",
        "slug": "another-slug"
    })
    assert response.status_code == 200
    assert "Email already registered" in response.text

def test_register_owner_duplicate_slug(client, test_db):
    create_test_owner(test_db, email="another@example.com", slug="duplicate-slug")
    response = client.post("/register", data={
        "name": "Duplicate Slug Owner",
        "email": "diff@example.com",
        "password": "password",
        "business_name": "Yet Another Business",
        "slug": "duplicate-slug"
    })
    assert response.status_code == 200
    assert "Business URL already taken" in response.text

def test_login_success(client, test_db):
    create_test_owner(test_db)
    response = client.post("/token", data={"username": "test@example.com", "password": "password"})
    assert response.status_code == 302 # Redirect to dashboard
    assert response.headers["location"] == "/dashboard"
    assert "access_token" in response.cookies

def test_login_invalid_credentials(client, test_db):
    create_test_owner(test_db)
    response = client.post("/token", data={"username": "test@example.com", "password": "wrongpassword"})
    assert response.status_code == 200
    assert "Incorrect email or password" in response.text

def test_dashboard_access_requires_login(client):
    response = client.get("/dashboard")
    assert response.status_code == 302 # Redirect to login if not authenticated
    assert response.headers["location"] == "/login"

def test_dashboard_access_authenticated(client, test_db):
    owner = create_test_owner(test_db)
    access_token = get_access_token(client, owner.email, "password")
    response = client.get("/dashboard", cookies={"access_token": access_token})
    assert response.status_code == 200
    assert "Welcome, Test Owner!" in response.text
    assert "Upcoming Bookings" in response.text

def test_logout(client, test_db):
    owner = create_test_owner(test_db)
    access_token = get_access_token(client, owner.email, "password")
    response = client.get("/logout", cookies={"access_token": access_token})
    assert response.status_code == 302
    assert response.headers["location"] == "/login"
    assert "access_token" not in response.cookies

def test_update_owner_profile(client, test_db):
    owner = create_test_owner(test_db)
    access_token = get_access_token(client, owner.email, "password")

    new_services = json.dumps([{"name": "New Service", "duration": 90, "price": 100.0}])
    new_availability = json.dumps({"Tuesday": [{"start_time": "10:00", "end_time": "18:00"}]})

    response = client.post(
        "/dashboard/profile",
        data={
            "name": "Updated Owner Name",
            "business_name": "Updated Business Name",
            "phone": "+9876543210",
            "services_json": new_services,
            "availability_json": new_availability,
        },
        cookies={"access_token": access_token}
    )
    assert response.status_code == 200
    assert "Profile updated successfully!" in response.text
    updated_owner = test_db.query(models.Owner).filter(models.Owner.id == owner.id).first()
    assert updated_owner.name == "Updated Owner Name"
    assert updated_owner.business_name == "Updated Business Name"
    assert updated_owner.phone == "+9876543210"
    assert updated_owner.services_json == new_services
    assert updated_owner.availability_json == new_availability

def test_booking_page_not_found(client):
    response = client.get("/non-existent-slug")
    assert response.status_code == 404
    assert "Booking page not found" in response.text

def test_booking_page_display(client, test_db):
    owner = create_test_owner(test_db)
    response = client.get(f"/{owner.slug}")
    assert response.status_code == 200
    assert "Test Business - Book an Appointment" in response.text
    assert "Service 1" in response.text
    assert "50.00 USD" in response.text # Test currency formatting

@patch("src.notifications.send_email_notification")
@patch("src.notifications.send_whatsapp_notification")
def test_submit_booking_success(mock_send_whatsapp, mock_send_email, client, test_db):
    owner = create_test_owner(test_db)
    booking_date = (datetime.date.today() + datetime.timedelta(days=7)).strftime("%Y-%m-%d")
    response = client.post(
        f"/{owner.slug}/book",
        data={
            "customer_name": "John Doe",
            "customer_email": "john.doe@example.com",
            "customer_phone": "+1987654321",
            "service_name": "Service 1",
            "booking_date": booking_date,
            "booking_time": "10:00 AM"
        }
    )
    assert response.status_code == 200
    assert "Your booking has been successfully confirmed!" in response.text

    booking = test_db.query(models.Booking).filter(models.Booking.customer_email == "john.doe@example.com").first()
    assert booking is not None
    assert booking.service_name == "Service 1"

    # Verify notifications were called
    assert mock_send_email.call_count == 2 # Owner and customer
    assert mock_send_whatsapp.call_count == 1 # Owner

@patch("src.notifications.send_email_notification")
@patch("src.notifications.send_whatsapp_notification")
def test_submit_booking_invalid_date_format(mock_send_whatsapp, mock_send_email, client, test_db):
    owner = create_test_owner(test_db)
    response = client.post(
        f"/{owner.slug}/book",
        data={
            "customer_name": "John Doe",
            "customer_email": "john.doe@example.com",
            "service_name": "Service 1",
            "booking_date": "invalid-date",
            "booking_time": "10:00 AM"
        }
    )
    assert response.status_code == 400
    assert "Invalid date or time format." in response.text
    assert mock_send_email.call_count == 0
    assert mock_send_whatsapp.call_count == 0

def test_i18n_language_toggle_on_login(client):
    response = client.post("/set-language", data={"lang": "ar"})
    assert response.status_code == 302
    assert response.headers["location"] == "/"
    assert response.cookies["lang"] == "ar"

    response = client.get("/", cookies={"lang": "ar"})
    assert "مرحباً" in response.text # Check for Arabic translation of "Welcome"

    response = client.post("/set-language", data={"lang": "fr"})
    response = client.get("/", cookies={"lang": "fr"})
    assert "Bienvenue" in response.text # Check for French translation of "Welcome"

def test_i18n_currency_formatting_arabic_locale(client, test_db):
    owner = create_test_owner(test_db, slug="currency-test")
    # Simulate setting Arabic language
    response = client.get(f"/{owner.slug}", cookies={"lang": "ar"})
    assert response.status_code == 200
    # Check for Arabic currency format (e.g., ٥٠٫٠٠ US$)
    # The actual output from babel format_currency(50.0, 'USD', locale='ar') is "US$ ٥٠٫٠٠"
    assert "US$ ٥٠٫٠٠" in response.text or "٥٠٫٠٠ US$" in response.text

def test_i18n_currency_formatting_french_locale(client, test_db):
    owner = create_test_owner(test_db, slug="currency-test-fr")
    # Simulate setting French language
    response = client.get(f"/{owner.slug}", cookies={"lang": "fr"})
    assert response.status_code == 200
    # Babel's format_currency for 'fr' locale with 'USD' might produce "50,00 $US"
    assert "50,00 $US" in response.text or "50,00 USD" in response.text # Accept variations

def test_error_handling_profile_update(client, test_db):
    owner = create_test_owner(test_db)
    access_token = get_access_token(client, owner.email, "password")

    # Simulate a malformed JSON for services
    response = client.post(
        "/dashboard/profile",
        data={
            "name": "Updated Owner Name",
            "business_name": "Updated Business Name",
            "phone": "+9876543210",
            "services_json": "invalid json here", # Malformed JSON
            "availability_json": json.dumps({"Monday": [{"start_time": "09:00", "end_time": "17:00"}]}),
        },
        cookies={"access_token": access_token}
    )
    assert response.status_code == 200 # Still 200, but with error message
    assert "Error updating profile:" in response.text
    assert "Expecting value" in response.text # JSONDecodeError message

def test_error_handling_booking_submission_invalid_email(client, test_db):
    owner = create_test_owner(test_db)
    booking_date = (datetime.date.today() + datetime.timedelta(days=7)).strftime("%Y-%m-%d")
    response = client.post(
        f"/{owner.slug}/book",
        data={
            "customer_name": "Invalid Email User",
            "customer_email": "invalid-email", # Invalid email format
            "service_name": "Service 1",
            "booking_date": booking_date,
            "booking_time": "10:00 AM"
        }
    )
    assert response.status_code == 400
    assert "value is not a valid email address" in response.text # Pydantic validation error
