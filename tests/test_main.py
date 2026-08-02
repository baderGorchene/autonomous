from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.main import app, get_db, oauth2_scheme, get_current_owner, get_templates, get_locale
from src.database import Base
from src.config import settings
from src import models, crud, security, schemas
import pytest
import os
from datetime import timedelta, datetime, date
import json
from fastapi import Request, Response

# Override settings for testing
settings.DATABASE_URL = "sqlite:///./test.db" # Use a separate test database
settings.TESTING = True # Flag for testing environment
settings.SECRET_KEY = "test-secret-key" # Use a simple key for testing
settings.ACCESS_TOKEN_EXPIRE_MINUTES = 1 # Short expiry for tests

# Setup test database
engine = create_engine(settings.DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create tables for testing
Base.metadata.create_all(bind=engine)

# Override the get_db dependency for tests
def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

# Override get_current_owner for tests (mock authenticated user)
def override_get_current_owner():
    # This mock owner should be created in the test database if needed
    # For now, return a dummy owner or fetch one if already created by a test setup
    return models.Owner(
        id=1,
        name="Test Owner",
        email="test@example.com",
        hashed_password=security.get_password_hash("testpassword"),
        business_name="Test Business",
        slug="test-business",
        services_json="[]",
        availability_json="{}",
        phone="+1234567890"
    )

app.dependency_overrides[get_current_owner] = override_get_current_owner

# Mock templates and i18n for simpler testing
from jinja2 import Environment, FileSystemLoader
from jinja2.ext import i18n
import gettext

class MockTranslations(gettext.NullTranslations):
    def gettext(self, message):
        return message # Simply return the original message for tests

def get_mock_jinja_env(locale='en'):
    env = Environment(loader=FileSystemLoader(os.path.join(settings.PROJECT_ROOT, 'templates')), extensions=[i18n])
    env.install_gettext_translations(MockTranslations())
    def urlencode_query_param(url, query_param_name, value):
        from urllib.parse import urlparse, urlunparse, parse_qs, urlencode
        parsed_url = urlparse(url)
        query_params = parse_qs(parsed_url.query)
        query_params[query_param_name] = [value]
        new_query = urlencode(query_params, doseq=True)
        return urlunparse(parsed_url._replace(query=new_query))
    env.filters['urlencode'] = urlencode_query_param
    return env

class MockJinja2Templates:
    def __init__(self, directory, env):
        self.env = env
    
    def TemplateResponse(self, name, context, status_code=200, headers=None, media_type="text/html"):
        template = self.env.get_template(name)
        return Response(template.render(context), status_code=status_code, headers=headers, media_type=media_type)

def override_get_templates(request: Request):
    locale = request.state.locale if hasattr(request.state, 'locale') else 'en'
    return MockJinja2Templates(directory=settings.TEMPLATES_DIR, env=get_mock_jinja_env(locale))

app.dependency_overrides[get_templates] = override_get_templates

# Test client
client = TestClient(app)

# Fixture to clear database before each test
@pytest.fixture(name="db")
def session_fixture():
    Base.metadata.drop_all(bind=engine) # Drop tables
    Base.metadata.create_all(bind=engine) # Recreate tables
    db = TestingSessionLocal()
    yield db
    db.close()

# Helper to get an auth token
def get_auth_token(email, password):
    response = client.post(
        "/token",
        data={"username": email, "password": password}
    )
    assert response.status_code == 200
    return response.json()["access_token"]

# --- Tests ---

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.text == "OK"

def test_signup_and_login(db: Session):
    # Test signup
    signup_response = client.post(
        "/signup",
        data={
            "name": "Test User",
            "email": "test@example.com",
            "password": "testpassword",
            "business_name": "Test Business",
            "slug": "test-business",
            "phone": "+1234567890"
        },
        follow_redirects=False
    )
    assert signup_response.status_code == 303 # Redirect to dashboard
    assert signup_response.headers["location"] == "/dashboard"

    # Verify owner created in DB
    owner = crud.get_owner_by_email(db, "test@example.com")
    assert owner is not None
    assert owner.name == "Test User"
    assert owner.slug == "test-business"

    # Test login with newly created user
    login_response = client.post(
        "/login",
        data={"email": "test@example.com", "password": "testpassword"},
        follow_redirects=False
    )
    assert login_response.status_code == 303 # Redirect to dashboard
    assert login_response.headers["location"] == "/dashboard"
    
    # Check if access_token cookie is set
    assert "access_token" in login_response.cookies

def test_duplicate_email_signup(db: Session):
    # First signup
    client.post(
        "/signup",
        data={
            "name": "User One", "email": "duplicate@example.com", "password": "password1",
            "business_name": "Business One", "slug": "business-one"
        }
    )
    # Second signup with same email
    response = client.post(
        "/signup",
        data={
            "name": "User Two", "email": "duplicate@example.com", "password": "password2",
            "business_name": "Business Two", "slug": "business-two"
        }
    )
    assert response.status_code == 400 # Should fail due to duplicate email

def test_duplicate_slug_signup(db: Session):
    # First signup
    client.post(
        "/signup",
        data={
            "name": "User One", "email": "user1@example.com", "password": "password1",
            "business_name": "Business One", "slug": "duplicate-slug"
        }
    )
    # Second signup with same slug
    response = client.post(
        "/signup",
        data={
            "name": "User Two", "email": "user2@example.com", "password": "password2",
            "business_name": "Business Two", "slug": "duplicate-slug"
        }
    )
    assert response.status_code == 400 # Should fail due to duplicate slug

def test_dashboard_access_unauthenticated():
    response = client.get("/dashboard")
    assert response.status_code == 401 # Should require authentication

def test_dashboard_access_authenticated(db: Session):
    # Create an owner
    owner_data = schemas.OwnerCreate(
        name="Auth User", email="auth@example.com", password="authpassword",
        business_name="Auth Business", slug="auth-business", phone="+1112223333"
    )
    crud.create_owner(db, owner_data)

    # Get token
    access_token = get_auth_token("auth@example.com", "authpassword")
    
    # Access dashboard with token
    response = client.get(
        "/dashboard",
        cookies={"access_token": access_token}
    )
    assert response.status_code == 200
    assert "Auth User" in response.text
    assert "Auth Business" in response.text
    assert "bookslot.app/auth-business" in response.text

def test_profile_update(db: Session):
    owner_data = schemas.OwnerCreate(
        name="Update User", email="update@example.com", password="updatepassword",
        business_name="Update Business", slug="update-business", phone="+1112223333"
    )
    crud.create_owner(db, owner_data)
    access_token = get_auth_token("update@example.com", "updatepassword")

    updated_services = [
        {"name": "Haircut", "duration": 30, "price": 25.0, "description": "Standard haircut"},
        {"name": "Coloring", "duration": 90, "price": 80.0, "description": "Hair coloring"}
    ]
    updated_availability = {
        "Monday": [{"day_of_week": "Monday", "start_time": "09:00", "end_time": "17:00"}],
        "Tuesday": [{"day_of_week": "Tuesday", "start_time": "10:00", "end_time": "18:00"}]
    }

    response = client.post(
        "/profile",
        data={
            "name": "Updated Name",
            "business_name": "Updated Business Name",
            "phone": "+9876543210",
            "services_json": json.dumps(updated_services),
            "availability_json": json.dumps(updated_availability)
        },
        cookies={"access_token": access_token},
        follow_redirects=False
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/dashboard"

    # Verify changes in DB
    owner = crud.get_owner_by_email(db, "update@example.com")
    assert owner.name == "Updated Name"
    assert owner.business_name == "Updated Business Name"
    assert owner.phone == "+9876543210"
    assert json.loads(owner.services_json) == updated_services
    assert json.loads(owner.availability_json) == updated_availability

def test_public_booking_page_not_found():
    response = client.get("/bookslot.app/non-existent-slug")
    assert response.status_code == 404

def test_public_booking_page_display(db: Session):
    owner_data = schemas.OwnerCreate(
        name="Booking Owner", email="booking@example.com", password="bookingpassword",
        business_name="Booking Co.", slug="booking-co"
    )
    db_owner = crud.create_owner(db, owner_data)
    
    db_owner.services_json = json.dumps([{"name": "Consultation", "duration": 60, "price": 50.0}])
    db_owner.availability_json = json.dumps({"Monday": [{"day_of_week": "Monday", "start_time": "09:00", "end_time": "17:00"}]})
    db.add(db_owner)
    db.commit()
    db.refresh(db_owner)

    response = client.get("/bookslot.app/booking-co")
    assert response.status_code == 200
    assert "Booking Co." in response.text
    assert "Consultation" in response.text

def test_submit_booking(db: Session, monkeypatch):
    owner_data = schemas.OwnerCreate(
        name="Bookable Owner", email="bookable@example.com", password="bookablepassword",
        business_name="Bookable Services", slug="bookable-services", phone="+15551234567"
    )
    db_owner = crud.create_owner(db, owner_data)
    db_owner.services_json = json.dumps([{"name": "Quick Chat", "duration": 30, "price": 0.0}])
    db_owner.availability_json = json.dumps({"Monday": [{"day_of_week": "Monday", "start_time": "09:00", "end_time": "17:00"}]})
    db.add(db_owner)
    db.commit()
    db.refresh(db_owner)

    # Mock notification functions to prevent actual external calls
    monkeypatch.setattr("src.notifications.send_email", lambda *args, **kwargs: True)
    monkeypatch.setattr("src.notifications.send_whatsapp_message", lambda *args, **kwargs: True)

    booking_date = (date.today() + timedelta(days=7)).strftime("%Y-%m-%d") # A future Monday
    if datetime.strptime(booking_date, "%Y-%m-%d").weekday() != 0: # 0 is Monday
        booking_date = (date.today() + timedelta(days=(7 - date.today().weekday()) % 7)).strftime("%Y-%m-%d")


    response = client.post(
        "/bookslot.app/bookable-services/book",
        data={
            "customer_name": "Jane Doe",
            "customer_email": "jane@example.com",
            "customer_phone": "+1234567890",
            "service_name": "Quick Chat",
            "booking_date_str": booking_date,
            "booking_time": "10:00 AM"
        },
        follow_redirects=False
    )
    assert response.status_code == 303
    assert "/bookable-services/confirm" in response.headers["location"]

    # Verify booking in DB
    bookings = db.query(models.Booking).filter(models.Booking.owner_id == db_owner.id).all()
    assert len(bookings) == 1
    assert bookings[0].customer_name == "Jane Doe"
    assert bookings[0].service_name == "Quick Chat"
    assert bookings[0].booking_date == datetime.strptime(booking_date, "%Y-%m-%d").date()

def test_booking_confirmation_page(db: Session):
    owner_data = schemas.OwnerCreate(
        name="Confirm Owner", email="confirm@example.com", password="confirm_password",
        business_name="Confirm Business", slug="confirm-business"
    )
    db_owner = crud.create_owner(db, owner_data)

    booking_date = date.today() + timedelta(days=1)
    booking_create = schemas.BookingCreate(
        customer_name="Confirm Customer",
        customer_email="confirm_customer@example.com",
        service_name="Test Service",
        booking_date=booking_date,
        booking_time="11:00 AM"
    )
    db_booking = crud.create_booking(db, booking_create, db_owner.id)

    response = client.get(f"/bookslot.app/confirm-business/confirm?booking_id={db_booking.id}")
    assert response.status_code == 200
    assert "Booking Confirmed!" in response.text
    assert "Confirm Customer" in response.text
    assert "Confirm Business" in response.text
    assert "Test Service" in response.text
    assert "11:00 AM" in response.text

def test_i18n_language_toggle_query_param(db: Session):
    # Test setting language via query parameter
    response_ar = client.get("/?lang=ar")
    assert response_ar.status_code == 200
    # In mock setup, it returns original message, but cookie should be set
    assert response_ar.cookies.get("lang") == "ar"

    response_fr = client.get("/?lang=fr")
    assert response_fr.status_code == 200
    assert response_fr.cookies.get("lang") == "fr"

    response_en = client.get("/?lang=en")
    assert response_en.status_code == 200
    assert response_en.cookies.get("lang") == "en"

def test_i18n_language_toggle_cookie(db: Session):
    # Test setting language via cookie
    response_ar = client.get("/", cookies={"lang": "ar"})
    assert response_ar.status_code == 200
    assert response_ar.cookies.get("lang") == "ar"

    response_fr = client.get("/", cookies={"lang": "fr"})
    assert response_fr.status_code == 200
    assert response_fr.cookies.get("lang") == "fr"

def test_i18n_language_priority_query_over_cookie(db: Session):
    # Query param should override cookie
    response = client.get("/?lang=fr", cookies={"lang": "ar"})
    assert response.status_code == 200
    assert response.cookies.get("lang") == "fr" # New cookie should be set to 'fr'

def test_i18n_language_priority_accept_language_header(db: Session):
    # If no query or cookie, use header
    response_ar = client.get("/", headers={"Accept-Language": "ar,en-US;q=0.7,en;q=0.3"})
    assert response_ar.status_code == 200
    assert response_ar.cookies.get("lang") == "ar"

    response_fr = client.get("/", headers={"Accept-Language": "fr-CA,fr;q=0.9,en;q=0.8"})
    assert response_fr.status_code == 200
    assert response_fr.cookies.get("lang") == "fr"

    response_en = client.get("/", headers={"Accept-Language": "en-US,en;q=0.9"})
    assert response_en.status_code == 200
    assert response_en.cookies.get("lang") == "en"
