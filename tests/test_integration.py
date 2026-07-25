import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import json

from src.main import app, get_db
from src import models, schemas, security, crud, notifications

client = TestClient(app)

# Fixture for a mock database session
@pytest.fixture
def mock_db_session():
    db_mock = MagicMock(spec=Session)
    yield db_mock

# Override the get_db dependency to use the mock session
@pytest.fixture(autouse=True)
def override_get_db(mock_db_session):
    app.dependency_overrides[get_db] = lambda: mock_db_session
    yield
    app.dependency_overrides.clear()

# Fixture for a mock current owner
@pytest.fixture
def mock_owner():
    owner = models.Owner(
        id=1,
        name="Test Owner",
        email="owner@example.com",
        hashed_password=security.get_password_hash("testpassword"),
        business_name="Test Business",
        slug="test-business",
        services_json=json.dumps([{"name": "Haircut", "duration_minutes": 30, "price": 25.0}]),
        availability_json=json.dumps({"Monday": [{"day_of_week": "Monday", "start_time": "09:00", "end_time": "17:00"}]}),
        phone="+1234567890"
    )
    return owner

# Override get_current_owner for authenticated routes
@pytest.fixture(autouse=True)
def override_get_current_owner(mock_owner):
    with patch('src.security.get_current_owner') as mock_dependency:
        mock_dependency.return_value = mock_owner
        yield

# Mock notification services
@pytest.fixture(autouse=True)
def mock_notifications():
    with patch('src.notifications.send_email_notification') as mock_send_email,
         patch('src.notifications.send_whatsapp_notification') as mock_send_whatsapp:
        mock_send_email.return_value = True
        mock_send_whatsapp.return_value = True
        yield mock_send_email, mock_send_whatsapp


# --- Health Check Test ---
def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

# --- Owner Registration & Authentication Tests ---
def test_register_owner(mock_db_session):
    mock_db_session.query.return_value.filter.return_value.first.side_effect = [None, None] # No owner by email, no owner by slug
    mock_db_session.add.return_value = None
    mock_db_session.commit.return_value = None
    mock_db_session.refresh.return_value = models.Owner(id=1, email="new@example.com", name="New Owner", business_name="New Biz", slug="new-biz", hashed_password="hashed", services_json="[]", availability_json="{}")

    response = client.post(
        "/register",
        json={"email": "new@example.com", "password": "newpass", "name": "New Owner", "business_name": "New Biz", "slug": "new-biz"}
    )
    assert response.status_code == 200
    assert response.json()["email"] == "new@example.com"

def test_register_owner_email_exists(mock_db_session, mock_owner):
    mock_db_session.query.return_value.filter.return_value.first.return_value = mock_owner # Owner with email exists
    response = client.post(
        "/register",
        json={"email": "owner@example.com", "password": "newpass", "name": "New Owner", "business_name": "New Biz", "slug": "new-biz"}
    )
    assert response.status_code == 400
    assert "Email already registered" in response.json()["detail"]

def test_login_for_access_token(mock_db_session, mock_owner):
    with patch('src.crud.authenticate_owner', return_value=mock_owner):
        response = client.post(
            "/token",
            data={"username": "owner@example.com", "password": "testpassword"}
        )
        assert response.status_code == 200
        assert "access_token" in response.json()

def test_login_for_access_token_invalid_credentials(mock_db_session):
    with patch('src.crud.authenticate_owner', return_value=False):
        response = client.post(
            "/token",
            data={"username": "wrong@example.com", "password": "wrongpass"}
        )
        assert response.status_code == 401
        assert "Incorrect email or password" in response.json()["detail"]

# --- Owner Dashboard Tests ---
def test_owner_dashboard_get(mock_db_session, mock_owner):
    mock_db_session.query.return_value.filter.return_value.order_by.return_value.all.return_value = [] # No upcoming bookings
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert "Welcome, Test Owner!" in response.text
    assert "Your Profile" in response.text
    assert "Upcoming Bookings" in response.text
    assert "Haircut" in response.text # Check for service from mock_owner
    assert "Monday" in response.text # Check for availability from mock_owner

def test_owner_profile_update(mock_db_session, mock_owner):
    mock_db_session.add.return_value = None
    mock_db_session.commit.return_value = None
    mock_db_session.refresh.return_value = mock_owner # Refresh returns the same mock_owner updated
    mock_db_session.query.return_value.filter.return_value.order_by.return_value.all.return_value = []

    updated_services = json.dumps([{"name": "Updated Service", "duration_minutes": 45, "price": 75.0}])
    updated_availability = json.dumps({"Tuesday": [{"day_of_week": "Tuesday", "start_time": "08:00", "end_time": "16:00"}]})

    response = client.post(
        "/owner/profile",
        data={
            "name": "Updated Name",
            "business_name": "Updated Business",
            "phone": "+1987654321",
            "services_json": updated_services,
            "availability_json": updated_availability
        }
    )
    assert response.status_code == 200
    assert "Profile updated successfully!" in response.text
    assert "Updated Name" in response.text
    assert "Updated Business" in response.text
    # Verify that the mock_owner object was updated
    assert mock_owner.name == "Updated Name"
    assert mock_owner.business_name == "Updated Business"
    assert mock_owner.phone == "+1987654321"
    assert mock_owner.services_json == updated_services
    assert mock_owner.availability_json == updated_availability

def test_owner_profile_update_invalid_json(mock_db_session, mock_owner):
    response = client.post(
        "/owner/profile",
        data={
            "name": "Updated Name",
            "business_name": "Updated Business",
            "phone": "+1987654321",
            "services_json": "invalid json",
            "availability_json": "{}"
        }
    )
    assert response.status_code == 400
    assert "Invalid JSON format for services or availability" in response.json()["detail"]

# --- Public Booking Page Tests ---
def test_public_booking_page_get(mock_db_session, mock_owner):
    with patch('src.crud.get_owner_by_slug', return_value=mock_owner):
        response = client.get(f"/book/{mock_owner.slug}")
        assert response.status_code == 200
        assert f"<title>{mock_owner.business_name} - Book an Appointment</title>" in response.text
        assert "Haircut" in response.text # Check service

def test_public_booking_page_not_found(mock_db_session):
    mock_db_session.query.return_value.filter.return_value.first.return_value = None # Owner not found
    response = client.get("/book/non-existent-slug")
    assert response.status_code == 404
    assert "Owner not found" in response.json()["detail"]

def test_submit_booking_success(mock_db_session, mock_owner, mock_notifications):
    mock_db_session.query.return_value.filter.return_value.first.return_value = mock_owner # For getting owner by slug
    mock_db_session.add.return_value = None
    mock_db_session.commit.return_value = None
    mock_db_session.refresh.return_value = MagicMock(spec=models.Booking) # Mock the created booking object

    booking_time_str = (datetime.now() + timedelta(days=1)).isoformat()

    response = client.post(
        f"/book/{mock_owner.slug}",
        data={
            "customer_name": "John Doe",
            "customer_email": "john@example.com",
            "customer_phone": "+11234567890",
            "service_name": "Haircut",
            "booking_time": booking_time_str
        },
        follow_redirects=False # Do not follow redirect to check status code
    )
    assert response.status_code == 303 # Redirect to confirmation page
    assert "/booking-confirmation" in response.headers["location"]
    mock_notifications[0].assert_called_with(
        recipient_email=mock_owner.email,
        subject="New Booking Received!",
        body=f"You have a new booking from John Doe for Haircut at {booking_time_str}. Customer email: john@example.com, phone: +11234567890"
    )
    mock_notifications[0].assert_called_with(
        recipient_email="john@example.com",
        subject="Your Booking Confirmation",
        body=f"Hi John Doe, your booking for Haircut with Test Business at {booking_time_str} is confirmed."
    )
    mock_notifications[1].assert_any_call(
        recipient_phone=mock_owner.phone,
        message=f"New BookSlot booking! John Doe for Haircut at {booking_time_str}. Email: john@example.com, Phone: +11234567890"
    )
    mock_notifications[1].assert_any_call(
        recipient_phone="+11234567890",
        message=f"Your BookSlot booking for Haircut with Test Business at {booking_time_str} is confirmed."
    )

def test_submit_booking_error_rendering(mock_db_session, mock_owner, mock_notifications):
    mock_db_session.query.return_value.filter.return_value.first.return_value = mock_owner # For getting owner by slug
    # Simulate a database error during booking creation
    mock_db_session.add.side_effect = Exception("DB Error")

    booking_time_str = (datetime.now() + timedelta(days=1)).isoformat()

    response = client.post(
        f"/book/{mock_owner.slug}",
        data={
            "customer_name": "Jane Doe",
            "customer_email": "jane@example.com",
            "service_name": "Haircut",
            "booking_time": booking_time_str
        }
    )
    assert response.status_code == 200 # Renders the page again with an error
    assert "There was an error processing your booking. Please try again." in response.text
    mock_notifications[0].assert_not_called()
    mock_notifications[1].assert_not_called()

# --- Booking Confirmation Page Tests ---
def test_booking_confirmation_page_get(mock_db_session, mock_owner):
    with patch('src.crud.get_owner_by_slug', return_value=mock_owner):
        response = client.get(f"/booking-confirmation/{mock_owner.slug}")
        assert response.status_code == 200
        assert "Booking Confirmed!" in response.text
        assert f"Thank you for booking with {mock_owner.business_name}." in response.text

def test_booking_confirmation_page_owner_not_found(mock_db_session):
    mock_db_session.query.return_value.filter.return_value.first.return_value = None # Owner not found
    response = client.get("/booking-confirmation/non-existent-slug")
    assert response.status_code == 404
    assert "Owner not found" in response.json()["detail"]
