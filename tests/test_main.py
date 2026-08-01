import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.main import app, get_db, get_current_owner # Assuming templates and get_jinja_env are handled by the middleware/imported in main
from src.database import Base
from src.models import Owner, Booking
from src.schemas import OwnerCreate
from src.security import get_password_hash
from src.config import settings
import os
import gettext
from unittest.mock import patch

# --- Test Database Setup ---
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(name="db_session")
def db_session_fixture():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine) # Clean up after each test

@pytest.fixture(name="client")
def client_fixture(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    # Mock authentication for tests that require it, unless specifically testing auth failure
    app.dependency_overrides[get_current_owner] = lambda: Owner(
        id=1, name="Test Owner", email="test@example.com", hashed_password=get_password_hash("password"),
        business_name="Test Business", slug="test-business", services_json="[]", availability_json="{}", phone="1234567890"
    )
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear() # Clear overrides after test

# --- Mocking external services for tests ---
@pytest.fixture(autouse=True)
def mock_notifications():
    with patch('src.notifications.send_email') as mock_send_email, \
         patch('src.notifications.send_whatsapp_message') as mock_send_whatsapp:
        yield mock_send_email, mock_send_whatsapp

# --- Tests ---

def test_read_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_signup_owner(client, db_session):
    response = client.post(
        "/signup",
        json={
            "name": "New Owner",
            "email": "new@example.com",
            "password": "newpassword",
            "business_name": "New Business",
            "slug": "new-business",
            "phone": "0987654321"
        },
    )
    assert response.status_code == 200
    assert "access_token" in response.json()
    assert response.json()["token_type"] == "bearer"
    owner = db_session.query(Owner).filter(Owner.email == "new@example.com").first()
    assert owner is not None
    assert owner.name == "New Owner"

def test_signup_owner_duplicate_email(client, db_session):
    # First signup
    client.post(
        "/signup",
        json={
            "name": "Existing Owner",
            "email": "existing@example.com",
            "password": "password",
            "business_name": "Existing Business",
            "slug": "existing-business",
            "phone": "1111111111"
        },
    )
    # Second signup with same email
    response = client.post(
        "/signup",
        json={
            "name": "Another Owner",
            "email": "existing@example.com",
            "password": "anotherpassword",
            "business_name": "Another Business",
            "slug": "another-business",
            "phone": "2222222222"
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Email already registered"

def test_login_for_access_token(client, db_session):
    # Create an owner first
    hashed_password = get_password_hash("testpassword")
    db_session.add(Owner(name="Login Test", email="login@example.com", hashed_password=hashed_password,
                         business_name="Login Business", slug="login-business", services_json="[]", availability_json="{}", phone="1234567890"))
    db_session.commit()

    response = client.post(
        "/token",
        data={"username": "login@example.com", "password": "testpassword"},
    )
    assert response.status_code == 200
    assert "access_token" in response.json()
    assert response.json()["token_type"] == "bearer"

def test_login_for_access_token_invalid_credentials(client):
    response = client.post(
        "/token",
        data={"username": "nonexistent@example.com", "password": "wrongpassword"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect username or password"

def test_read_dashboard_unauthenticated(client):
    # Temporarily remove the get_current_owner override for this test
    original_override = app.dependency_overrides.get(get_current_owner)
    del app.dependency_overrides[get_current_owner]
    try:
        response = client.get("/dashboard")
        assert response.status_code == 302 # Redirect to login
        assert "/login" in response.headers["location"]
    finally:
        if original_override:
            app.dependency_overrides[get_current_owner] = original_override
        else:
            # If it was never set, ensure it's removed if it somehow got added
            if get_current_owner in app.dependency_overrides:
                del app.dependency_overrides[get_current_owner]


def test_read_dashboard_authenticated(client, db_session):
    # The client fixture already sets a mock authenticated owner
    # Create some bookings for this owner
    owner_id = app.dependency_overrides[get_current_owner]().id # Get ID from mock owner
    db_session.add(Booking(owner_id=owner_id, customer_name="Customer 1", customer_email="c1@example.com",
                           service_name="Haircut", booking_date="2024-12-01", booking_time="10:00", customer_phone="111"))
    db_session.add(Booking(owner_id=owner_id, customer_name="Customer 2", customer_email="c2@example.com",
                           service_name="Manicure", booking_date="2024-12-02", booking_time="14:00", customer_phone="222"))
    db_session.commit()

    response = client.get("/dashboard")
    assert response.status_code == 200
    assert "Test Business Dashboard" in response.text
    assert "Customer 1" in response.text
    assert "Haircut" in response.text
    assert "Customer 2" in response.text
    assert "Manicure" in response.text

def test_update_owner_profile(client, db_session):
    # The client fixture already sets a mock authenticated owner (id=1)
    # Ensure there's a real owner in the DB matching the mock for update
    owner = Owner(id=1, name="Original Name", email="test@example.com", hashed_password=get_password_hash("password"),
                  business_name="Original Business", slug="test-business", services_json="[]", availability_json="{}", phone="1234567890")
    db_session.add(owner)
    db_session.commit()
    db_session.refresh(owner)

    response = client.post(
        "/dashboard/profile",
        data={
            "name": "Updated Name",
            "business_name": "Updated Business",
            "phone": "0987654321",
            "services_json": '[{"name": "Service A", "duration": 30}]',
            "availability_json": '{"Monday": ["09:00-17:00"]}'
        },
        follow_redirects=True # Follow the redirect after successful update
    )
    assert response.status_code == 200 # Should be 200 after redirect to dashboard
    assert "Profile updated successfully!" in response.text

    updated_owner = db_session.query(Owner).filter(Owner.id == owner.id).first()
    assert updated_owner.name == "Updated Name"
    assert updated_owner.business_name == "Updated Business"
    assert updated_owner.phone == "0987654321"
    assert updated_owner.services_json == '[{"name": "Service A", "duration": 30}]'
    assert updated_owner.availability_json == '{"Monday": ["09:00-17:00"]}'

def test_public_booking_page_display(client, db_session):
    # Create an owner with services and availability
    owner = Owner(name="Public Owner", email="public@example.com", hashed_password=get_password_hash("password"),
                  business_name="Public Business", slug="public-business",
                  services_json='[{"name": "Consultation", "duration": 60, "price": 50}]',
                  availability_json='{"Monday": ["09:00-17:00"]}', phone="9998887777")
    db_session.add(owner)
    db_session.commit()

    response = client.get("/bookslot/public-business")
    assert response.status_code == 200
    assert "Public Business" in response.text
    assert "Consultation" in response.text
    assert "Book your slot" in response.text

def test_public_booking_page_not_found(client):
    response = client.get("/bookslot/non-existent-business")
    assert response.status_code == 404
    assert "Business not found" in response.text

def test_submit_booking(client, db_session, mock_notifications):
    # Create an owner with services and availability
    owner = Owner(name="Booking Owner", email="booking@example.com", hashed_password=get_password_hash("password"),
                  business_name="Booking Business", slug="booking-business",
                  services_json='[{"name": "Service X", "duration": 30, "price": 25}]',
                  availability_json='{"Monday": ["09:00-17:00"]}', phone="1231231234")
    db_session.add(owner)
    db_session.commit()
    db_session.refresh(owner)

    booking_data = {
        "customer_name": "John Doe",
        "customer_email": "john.doe@example.com",
        "customer_phone": "+15551234567",
        "service_name": "Service X",
        "booking_date": "2024-12-25",
        "booking_time": "10:00",
        "notes": "Urgent appointment"
    }
    response = client.post(f"/bookslot/{owner.slug}", data=booking_data)
    assert response.status_code == 200 # Should redirect to confirmation page
    assert "Booking confirmed!" in response.text

    # Verify booking was created in DB
    booking = db_session.query(Booking).filter(Booking.customer_email == "john.doe@example.com").first()
    assert booking is not None
    assert booking.service_name == "Service X"
    assert booking.owner_id == owner.id

    # Verify notifications were sent
    mock_notifications[0].assert_called_once() # send_email
    mock_notifications[1].assert_called_once() # send_whatsapp_message

def test_submit_booking_invalid_data(client, db_session):
    owner = Owner(name="Invalid Data Owner", email="invalid@example.com", hashed_password=get_password_hash("password"),
                  business_name="Invalid Data Business", slug="invalid-data-business",
                  services_json='[{"name": "Service Y", "duration": 60, "price": 100}]',
                  availability_json='{"Monday": ["09:00-17:00"]}', phone="1231231234")
    db_session.add(owner)
    db_session.commit()
    db_session.refresh(owner)

    # Missing customer_name
    booking_data = {
        "customer_email": "invalid@example.com",
        "customer_phone": "+15551234567",
        "service_name": "Service Y",
        "booking_date": "2024-12-26",
        "booking_time": "11:00",
        "notes": ""
    }
    response = client.post(f"/bookslot/{owner.slug}", data=booking_data)
    assert response.status_code == 422 # FastAPI validation error

def test_i18n_dashboard_language_toggle(client, db_session):
    owner = Owner(id=1, name="Test Owner", email="test@example.com", hashed_password=get_password_hash("password"),
                  business_name="Test Business", slug="test-business", services_json="[]", availability_json="{}", phone="1234567890")
    db_session.add(owner)
    db_session.commit()

    # Test English (default)
    response_en = client.get("/dashboard")
    assert response_en.status_code == 200
    assert "Dashboard" in response_en.text
    assert "Upcoming Bookings" in response_en.text

    # Test Arabic
    response_ar = client.get("/dashboard?lang=ar")
    assert response_ar.status_code == 200
    # Assuming 'Dashboard' translates to 'لوحة القيادة' in ar/LC_MESSAGES/messages.po
    assert "لوحة القيادة" in response_ar.text
    assert "الحجوزات القادمة" in response_ar.text

    # Test French
    response_fr = client.get("/dashboard?lang=fr")
    assert response_fr.status_code == 200
    # Assuming 'Dashboard' translates to 'Tableau de bord' in fr/LC_MESSAGES/messages.po
    assert "Tableau de bord" in response_fr.text
    assert "Prochaines Réservations" in response_fr.text

def test_i18n_booking_page_language_toggle(client, db_session):
    # Create an owner
    owner = Owner(name="I18n Owner", email="i18n@example.com", hashed_password=get_password_hash("password"),
                  business_name="I18n Business", slug="i18n-business",
                  services_json='[{"name": "Service I18n", "duration": 30, "price": 10}]',
                  availability_json='{"Monday": ["09:00-17:00"]}', phone="1122334455")
    db_session.add(owner)
    db_session.commit()

    # Test English (default)
    response_en = client.get("/bookslot/i18n-business")
    assert response_en.status_code == 200
    assert "Book your slot" in response_en.text
    assert "Service I18n" in response_en.text

    # Test Arabic
    response_ar = client.get("/bookslot/i18n-business?lang=ar")
    assert response_ar.status_code == 200
    # Assuming 'Book your slot' translates to 'احجز موعدك'
    assert "احجز موعدك" in response_ar.text
    # Service name itself won't be translated by gettext, but surrounding text will be
    assert "Service I18n" in response_ar.text

    # Test French
    response_fr = client.get("/bookslot/i18n-business?lang=fr")
    assert response_fr.status_code == 200
    # Assuming 'Book your slot' translates to 'Réservez votre créneau'
    assert "Réservez votre créneau" in response_fr.text
    assert "Service I18n" in response_fr.text


# Additional test for error handling (e.g., service not found)
def test_submit_booking_service_not_found(client, db_session, mock_notifications):
    owner = Owner(name="Service Error Owner", email="serviceerror@example.com", hashed_password=get_password_hash("password"),
                  business_name="Service Error Business", slug="service-error-business",
                  services_json='[{"name": "Existing Service", "duration": 30, "price": 25}]',
                  availability_json='{"Monday": ["09:00-17:00"]}', phone="1231231234")
    db_session.add(owner)
    db_session.commit()
    db_session.refresh(owner)

    booking_data = {
        "customer_name": "John Doe",
        "customer_email": "john.doe@example.com",
        "customer_phone": "+15551234567",
        "service_name": "Non-existent Service", # This service does not exist
        "booking_date": "2024-12-25",
        "booking_time": "10:00",
        "notes": "Urgent appointment"
    }
    response = client.post(f"/bookslot/{owner.slug}", data=booking_data)
    assert response.status_code == 400
    assert "Invalid service selected." in response.text
    mock_notifications[0].assert_not_called()
    mock_notifications[1].assert_not_called()