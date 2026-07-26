import pytest
import datetime
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import os
import json

# Adjust path for import in test environment
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from main import app, get_db, PROJECT_ROOT
from database import Base
from config import settings
from models import Owner, Booking
from security import create_access_token

# Override settings for testing
settings.DATABASE_URL = "sqlite:///:memory:" # Use in-memory SQLite for tests
settings.SECRET_KEY = "test_secret_key"
settings.ALGORITHM = "HS256"
settings.ACCESS_TOKEN_EXPIRE_MINUTES = 1

# Setup test database
engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
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
        Base.metadata.drop_all(bind=engine)

@pytest.fixture(name="client")
def client_fixture(db_session):
    def override_get_db():
        yield db_session
    
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()

# Helper to create an owner and get a token
def create_test_owner_and_get_token(db_session):
    owner_data = {
        "name": "Test Owner",
        "email": "test@example.com",
        "hashed_password": "hashedpassword", # In real app, this would be hashed
        "business_name": "Test Business",
        "slug": "test-business",
        "services_json": json.dumps([{"name": "Haircut", "duration": 30, "price": 25.0}]),
        "availability_json": json.dumps({
            "Monday": [{"start_time": "09:00", "end_time": "17:00"}],
            "Tuesday": [{"start_time": "09:00", "end_time": "17:00"}],
            "Wednesday": [{"start_time": "09:00", "end_time": "17:00"}],
            "Thursday": [{"start_time": "09:00", "end_time": "17:00"}],
            "Friday": [{"start_time": "09:00", "end_time": "17:00"}],
        }),
        "phone": "+1234567890"
    }
    owner = Owner(**owner_data)
    db_session.add(owner)
    db_session.commit()
    db_session.refresh(owner)
    
    access_token = create_access_token(data={"sub": owner.email})
    return owner, access_token

# --- Core Functionality Tests ---

def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_register_owner(client, db_session):
    response = client.post(
        "/register",
        data={
            "name": "New Owner",
            "business_name": "New Biz",
            "slug": "new-biz",
            "email": "new@example.com",
            "password": "password123"
        },
        follow_redirects=False
    )
    assert response.status_code == 303 # Redirect to login
    assert response.headers['location'] == "/login"

    owner = db_session.query(Owner).filter(Owner.email == "new@example.com").first()
    assert owner is not None
    assert owner.name == "New Owner"

def test_register_owner_duplicate_email(client, db_session):
    client.post(
        "/register",
        data={
            "name": "Owner One", "business_name": "Biz One", "slug": "biz-one",
            "email": "duplicate@example.com", "password": "password123"
        }
    )
    response = client.post(
        "/register",
        data={
            "name": "Owner Two", "business_name": "Biz Two", "slug": "biz-two",
            "email": "duplicate@example.com", "password": "password456"
        }
    )
    assert response.status_code == 200 # Renders with error
    assert "Email already registered" in response.text

def test_register_owner_duplicate_slug(client, db_session):
    client.post(
        "/register",
        data={
            "name": "Owner One", "business_name": "Biz One", "slug": "duplicate-slug",
            "email": "owner1@example.com", "password": "password123"
        }
    )
    response = client.post(
        "/register",
        data={
            "name": "Owner Two", "business_name": "Biz Two", "slug": "duplicate-slug",
            "email": "owner2@example.com", "password": "password456"
        }
    )
    assert response.status_code == 200 # Renders with error
    assert "Business URL slug already taken" in response.text

def test_login_owner(client, db_session):
    client.post(
        "/register",
        data={
            "name": "Test Login", "business_name": "Login Biz", "slug": "login-biz",
            "email": "login@example.com", "password": "password123"
        }
    ) # Register first

    response = client.post(
        "/login",
        data={"username": "login@example.com", "password": "password123"},
        follow_redirects=False
    )
    assert response.status_code == 303
    assert response.headers['location'] == "/dashboard"
    assert "access_token" in response.cookies

def test_login_owner_invalid_credentials(client):
    response = client.post(
        "/login",
        data={"username": "nonexistent@example.com", "password": "wrongpassword"}
    )
    assert response.status_code == 200
    assert "Incorrect email or password" in response.text

def test_dashboard_access_authenticated(client, db_session):
    owner, access_token = create_test_owner_and_get_token(db_session)
    response = client.get(
        "/dashboard",
        cookies={"access_token": access_token}
    )
    assert response.status_code == 200
    assert f"Welcome, {owner.name}!" in response.text
    assert f"bookslot.app/{owner.slug}" in response.text

def test_dashboard_access_unauthenticated(client):
    response = client.get("/dashboard")
    assert response.status_code == 303 # Redirect to login
    assert response.headers['location'] == "/login"

def test_update_owner_profile(client, db_session):
    owner, access_token = create_test_owner_and_get_token(db_session)
    
    new_services = [
        {"name": "New Service 1", "duration": 60, "price": 50.0, "description": "Desc 1"},
        {"name": "New Service 2", "duration": 45}
    ]
    new_availability = {
        "Monday": [{"start_time": "10:00", "end_time": "18:00"}],
        "Saturday": [{"start_time": "10:00", "end_time": "14:00"}]
    }

    response = client.post(
        "/dashboard/profile",
        data={
            "name": "Updated Name",
            "business_name": "Updated Business",
            "phone": "+1987654321",
            "services": json.dumps(new_services),
            "availability": json.dumps(new_availability)
        },
        cookies={"access_token": access_token},
        follow_redirects=False
    )
    assert response.status_code == 303
    assert "success=Profile updated successfully" in response.headers['location']

    updated_owner = db_session.query(Owner).filter(Owner.id == owner.id).first()
    assert updated_owner.name == "Updated Name"
    assert updated_owner.business_name == "Updated Business"
    assert updated_owner.phone == "+1987654321"
    assert json.loads(updated_owner.services_json) == new_services
    assert json.loads(updated_owner.availability_json) == new_availability

def test_update_owner_profile_invalid_json(client, db_session):
    owner, access_token = create_test_owner_and_get_token(db_session)
    
    response = client.post(
        "/dashboard/profile",
        data={
            "name": "Updated Name",
            "business_name": "Updated Business",
            "phone": "+1987654321",
            "services": "invalid json", # Invalid
            "availability": json.dumps({"Monday": [{"start_time": "10:00", "end_time": "18:00"}]})
        },
        cookies={"access_token": access_token}
    )
    assert response.status_code == 200
    assert "Invalid services data" in response.text

def test_public_booking_page_get(client, db_session):
    owner, _ = create_test_owner_and_get_token(db_session)
    response = client.get(f"/{owner.slug}")
    assert response.status_code == 200
    assert owner.business_name in response.text
    assert "Haircut" in response.text # Service name

def test_public_booking_page_not_found(client):
    response = client.get("/non-existent-slug")
    assert response.status_code == 404
    assert "Owner not found" in response.text

def test_submit_booking(client, db_session, monkeypatch):
    owner, _ = create_test_owner_and_get_token(db_session)

    # Mock notification functions to prevent actual external calls during testing
    mock_send_email_called = False
    mock_send_whatsapp_called = False

    def mock_send_email(*args, **kwargs):
        nonlocal mock_send_email_called
        mock_send_email_called = True
        print(f"Mock send_email called: {args}")

    def mock_send_whatsapp_message(*args, **kwargs):
        nonlocal mock_send_whatsapp_called
        mock_send_whatsapp_called = True
        print(f"Mock send_whatsapp_message called: {args}")

    monkeypatch.setattr("src.notifications.send_email", mock_send_email)
    monkeypatch.setattr("src.notifications.send_whatsapp_message", mock_send_whatsapp_message)

    today = datetime.date.today()
    tomorrow = today + datetime.timedelta(days=1)
    booking_date_str = tomorrow.isoformat()
    booking_time = "10:00" # Assume this slot is available

    response = client.post(
        f"/{owner.slug}/book",
        data={
            "customer_name": "John Doe",
            "customer_email": "john.doe@example.com",
            "customer_phone": "+15551234567",
            "service_name": "Haircut",
            "booking_date": booking_date_str,
            "booking_time": booking_time,
            "notes": "Please be on time."
        }
    )
    assert response.status_code == 200
    assert "Booking Confirmed!" in response.text
    assert "Your booking has been successfully confirmed!" in response.text

    booking = db_session.query(Booking).filter(Booking.customer_email == "john.doe@example.com").first()
    assert booking is not None
    assert booking.service_name == "Haircut"
    assert booking.booking_date == tomorrow
    assert booking.booking_time == booking_time
    assert mock_send_email_called
    assert mock_send_whatsapp_called

def test_submit_booking_past_date_error(client, db_session):
    owner, _ = create_test_owner_and_get_token(db_session)
    yesterday = datetime.date.today() - datetime.timedelta(days=1)
    
    response = client.post(
        f"/{owner.slug}/book",
        data={
            "customer_name": "Jane Doe",
            "customer_email": "jane.doe@example.com",
            "service_name": "Haircut",
            "booking_date": yesterday.isoformat(),
            "booking_time": "10:00",
            "notes": "Should fail."
        }
    )
    assert response.status_code == 200
    assert "Cannot book for a past date." in response.text
    # Ensure it renders the booking page again with the error
    assert "Book an Appointment with" in response.text

# --- Internationalization (i18n) Tests ---

def test_language_toggle_on_index_page(client):
    response_en = client.get("/", cookies={"locale": "en"})
    assert response_en.status_code == 200
    assert "Welcome to BookSlot!" in response_en.text
    
    response_ar = client.get("/", cookies={"locale": "ar"})
    assert response_ar.status_code == 200
    assert "مرحباً بك في BookSlot!" in response_ar.text # Arabic translation
    
    response_fr = client.get("/", cookies={"locale": "fr"})
    assert response_fr.status_code == 200
    assert "Bienvenue sur BookSlot!" in response_fr.text # French translation

def test_language_toggle_on_dashboard(client, db_session):
    owner, access_token = create_test_owner_and_get_token(db_session)

    response_en = client.get("/dashboard", cookies={"access_token": access_token, "locale": "en"})
    assert response_en.status_code == 200
    assert "Welcome, Test Owner!" in response_en.text
    assert "Your Profile" in response_en.text

    response_ar = client.get("/dashboard", cookies={"access_token": access_token, "locale": "ar"})
    assert response_ar.status_code == 200
    assert "أهلاً بك، Test Owner!" in response_ar.text
    assert "ملفك الشخصي" in response_ar.text

    response_fr = client.get("/dashboard", cookies={"access_token": access_token, "locale": "fr"})
    assert response_fr.status_code == 200
    assert "Bienvenue, Test Owner!" in response_fr.text
    assert "Votre profil" in response_fr.text

def test_language_toggle_on_booking_page(client, db_session):
    owner, _ = create_test_owner_and_get_token(db_session)

    response_en = client.get(f"/{owner.slug}", cookies={"locale": "en"})
    assert response_en.status_code == 200
    assert "Book an Appointment with Test Business" in response_en.text
    assert "Select Service" in response_en.text

    response_ar = client.get(f"/{owner.slug}", cookies={"locale": "ar"})
    assert response_ar.status_code == 200
    assert "احجز موعداً مع Test Business" in response_ar.text
    assert "اختر الخدمة" in response_ar.text

    response_fr = client.get(f"/{owner.slug}", cookies={"locale": "fr"})
    assert response_fr.status_code == 200
    assert "Prendre un rendez-vous avec Test Business" in response_fr.text
    assert "Sélectionner un service" in response_fr.text

def test_set_locale_endpoint(client):
    response = client.get("/set_locale/fr", headers={"Referer": "/dashboard"}, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers['location'] == "/dashboard"
    assert response.cookies['locale'] == 'fr'
