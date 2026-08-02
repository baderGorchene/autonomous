import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Import application components
from src.main import app, get_db, get_templates
from src.database import Base
from src.config import settings
from src import models, security, crud, schemas
from src.i18n_config import get_jinja_env
from fastapi import Request
from starlette.datastructures import URL
from starlette.middleware.sessions import SessionMiddleware
import json
from datetime import datetime, timedelta
import mocker

# Override settings for testing
settings.TESTING = True
settings.DATABASE_URL = "sqlite:///:memory:" # Use in-memory SQLite for tests
settings.SECRET_KEY = "test-secret-key" # A simpler key for tests

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
def client_fixture(db_session: TestingSessionLocal):
    def override_get_db():
        try:
            yield db_session
        finally:
            db_session.close()
    
    # Mock get_templates to return a basic Jinja2Templates for testing
    def override_get_templates(request: Request):
        return get_jinja_env(locale=request.session.get("locale", "en"))

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_templates] = override_get_templates
    
    # Ensure the app has SessionMiddleware for testing session-dependent routes
    if not any(isinstance(m, SessionMiddleware) for m in app.user_middleware):
        app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

    with TestClient(app) as test_client:
        yield test_client

# Test cases
def test_read_root_redirects_to_login(client: TestClient):
    response = client.get("/")
    assert response.status_code == 302
    assert response.headers["location"] == "/login"

def test_login_page(client: TestClient):
    response = client.get("/login")
    assert response.status_code == 200
    assert "Login to BookSlot" in response.text

def test_signup_page(client: TestClient):
    response = client.get("/signup")
    assert response.status_code == 200
    assert "Sign Up for BookSlot" in response.text

def test_signup_owner(client: TestClient, db_session: TestingSessionLocal):
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
        follow_redirects=False # Do not follow redirect for status code check
    )
    assert response.status_code == 302
    assert response.headers["location"] == "/dashboard"

    owner = crud.get_owner_by_email(db_session, "test@example.com")
    assert owner is not None
    assert owner.name == "Test Owner"
    assert owner.business_name == "Test Business"
    assert owner.slug == "test-business"
    assert owner.phone == "+1234567890"
    assert security.verify_password("testpassword", owner.hashed_password)

def test_signup_duplicate_email(client: TestClient, db_session: TestingSessionLocal):
    # First signup
    client.post(
        "/signup",
        data={
            "name": "Test Owner", "email": "duplicate@example.com", "password": "password",
            "business_name": "Business One", "slug": "business-one"
        }
    )
    # Second signup with same email
    response = client.post(
        "/signup",
        data={
            "name": "Another Owner", "email": "duplicate@example.com", "password": "password",
            "business_name": "Business Two", "slug": "business-two"
        }
    )
    assert response.status_code == 200 # Should render signup page with error
    assert "Email already registered" in response.text

def test_signup_duplicate_slug(client: TestClient, db_session: TestingSessionLocal):
    # First signup
    client.post(
        "/signup",
        data={
            "name": "Test Owner", "email": "slug1@example.com", "password": "password",
            "business_name": "Business One", "slug": "duplicate-slug"
        }
    )
    # Second signup with same slug
    response = client.post(
        "/signup",
        data={
            "name": "Another Owner", "email": "slug2@example.com", "password": "password",
            "business_name": "Business Two", "slug": "duplicate-slug"
        }
    )
    assert response.status_code == 200 # Should render signup page with error
    assert "Custom URL already taken" in response.text

def test_login_owner(client: TestClient, db_session: TestingSessionLocal):
    crud.create_owner(
        db_session,
        schemas.OwnerCreate(
            name="Login User",
            email="login@example.com",
            password="loginpassword",
            business_name="Login Business",
            slug="login-business",
            phone=None
        )
    )
    response = client.post(
        "/login",
        data={"email": "login@example.com", "password": "loginpassword"},
        follow_redirects=False
    )
    assert response.status_code == 302
    assert response.headers["location"] == "/dashboard"
    # Check if session cookie is set
    assert "session" in client.cookies

def test_login_invalid_credentials(client: TestClient, db_session: TestingSessionLocal):
    response = client.post(
        "/login",
        data={"email": "nonexistent@example.com", "password": "wrongpassword"}
    )
    assert response.status_code == 200
    assert "Incorrect email or password" in response.text

def test_dashboard_access_unauthenticated(client: TestClient):
    response = client.get("/dashboard", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/login"

def test_dashboard_access_authenticated(client: TestClient, db_session: TestingSessionLocal):
    owner_data = schemas.OwnerCreate(
        name="Dashboard User", email="dash@example.com", password="dashpassword",
        business_name="Dashboard Biz", slug="dash-biz", phone=None
    )
    owner = crud.create_owner(db_session, owner_data)

    # Login and get session
    login_response = client.post(
        "/login",
        data={"email": "dash@example.com", "password": "dashpassword"},
        follow_redirects=False
    )
    assert login_response.status_code == 302

    # Now access dashboard with session
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert "Welcome, Dashboard User!" in response.text
    assert "No upcoming bookings." in response.text

def test_profile_update(client: TestClient, db_session: TestingSessionLocal):
    owner_data = schemas.OwnerCreate(
        name="Old Name", email="profile@example.com", password="password",
        business_name="Old Business", slug="profile-biz", phone="+1111111111"
    )
    owner = crud.create_owner(db_session, owner_data)

    # Login
    client.post(
        "/login",
        data={"email": "profile@example.com", "password": "password"}
    )

    # Update profile
    response = client.post(
        "/profile",
        data={
            "name": "New Name",
            "business_name": "New Business Inc.",
            "phone": "+9999999999"
        }
    )
    assert response.status_code == 200
    assert "Profile updated successfully!" in response.text
    
    updated_owner = crud.get_owner_by_email(db_session, "profile@example.com")
    assert updated_owner.name == "New Name"
    assert updated_owner.business_name == "New Business Inc."
    assert updated_owner.phone == "+9999999999"

def test_setup_services_and_availability(client: TestClient, db_session: TestingSessionLocal):
    owner_data = schemas.OwnerCreate(
        name="Service User", email="service@example.com", password="password",
        business_name="Service Biz", slug="service-biz", phone=None
    )
    owner = crud.create_owner(db_session, owner_data)

    client.post("/login", data={"email": "service@example.com", "password": "password"})

    # Update services
    services_payload = json.dumps([
        {"name": "Haircut", "duration": 30, "price": 25.0, "description": "Standard haircut"},
        {"name": "Coloring", "duration": 90, "price": 80.0, "description": ""}
    ])
    response = client.post("/setup-services", data={"services_data": services_payload})
    assert response.status_code == 200
    assert "Services updated successfully!" in response.text
    
    updated_owner = crud.get_owner_by_email(db_session, "service@example.com")
    assert json.loads(updated_owner.services_json) == json.loads(services_payload)

    # Update availability
    availability_payload = json.dumps({
        "Monday": ["09:00", "10:00", "11:00"],
        "Wednesday": ["14:00", "15:00"]
    })
    response = client.post("/setup-availability", data={"availability_data": availability_payload})
    assert response.status_code == 200
    assert "Availability updated successfully!" in response.text

    updated_owner = crud.get_owner_by_email(db_session, "service@example.com")
    assert json.loads(updated_owner.availability_json) == json.loads(availability_payload)

def test_public_booking_page_not_found(client: TestClient):
    response = client.get("/nonexistent-slug")
    assert response.status_code == 404
    assert "Booking page not found" in response.json()["detail"]

def test_public_booking_page_display(client: TestClient, db_session: TestingSessionLocal):
    owner_data = schemas.OwnerCreate(
        name="Public User", email="public@example.com", password="password",
        business_name="Public Business", slug="public-biz", phone=None
    )
    owner = crud.create_owner(db_session, owner_data)
    
    services_payload = json.dumps([{"name": "Basic Service", "duration": 60, "price": 50.0}])
    owner.services_json = services_payload
    db_session.add(owner);
    db_session.commit();

    response = client.get("/public-biz")
    assert response.status_code == 200
    assert "Public Business - Book Now" in response.text
    assert "Basic Service" in response.text

def test_submit_booking(client: TestClient, db_session: TestingSessionLocal, mocker):
    # Mock notification functions to prevent actual external calls
    mocker.patch("src.notifications.send_email_notification")
    mocker.patch("src.notifications.send_whatsapp_notification")

    owner_data = schemas.OwnerCreate(
        name="Booking Owner", email="booking@example.com", password="password",
        business_name="Booking Co.", slug="booking-co", phone="+15551234567"
    )
    owner = crud.create_owner(db_session, owner_data)
    
    services_payload = json.dumps([{"name": "Consultation", "duration": 30, "price": 100.0}])
    owner.services_json = services_payload
    db_session.add(owner);
    db_session.commit();

    booking_date = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
    response = client.post(
        f"/{owner.slug}/book",
        data={
            "customer_name": "John Doe",
            "customer_email": "john.doe@example.com",
            "customer_phone": "+1234567890",
            "service_name": "Consultation",
            "booking_date": booking_date,
            "booking_time": "10:00 AM"
        }
    )
    assert response.status_code == 200
    assert "Booking Confirmed!" in response.text
    assert "John Doe" in response.text
    assert "Consultation" in response.text
    assert "10:00 AM" in response.text

    # Verify notifications were called
    assert notifications.send_email_notification.called
    assert notifications.send_whatsapp_notification.called

    booking = db_session.query(models.Booking).filter_by(customer_email="john.doe@example.com").first()
    assert booking is not None
    assert booking.owner_id == owner.id
    assert booking.service_name == "Consultation"
    assert booking.booking_date.strftime("%Y-%m-%d") == booking_date
    assert booking.booking_time == "10:00 AM"

def test_submit_booking_invalid_date_format(client: TestClient, db_session: TestingSessionLocal):
    owner_data = schemas.OwnerCreate(
        name="Booking Owner", email="invaliddate@example.com", password="password",
        business_name="Invalid Date Co.", slug="invalid-date-co", phone=None
    )
    owner = crud.create_owner(db_session, owner_data)
    
    services_payload = json.dumps([{"name": "Service", "duration": 60, "price": 50.0}])
    owner.services_json = services_payload
    db_session.add(owner);
    db_session.commit();

    response = client.post(
        f"/{owner.slug}/book",
        data={
            "customer_name": "Jane Doe",
            "customer_email": "jane.doe@example.com",
            "service_name": "Service",
            "booking_date": "2024/01/01", # Invalid format
            "booking_time": "10:00 AM"
        }
    )
    assert response.status_code == 200
    assert "Invalid date format. Please use YYYY-MM-DD." in response.text

def test_i18n_language_toggle(client: TestClient, db_session: TestingSessionLocal):
    # Test setting language via query param
    response = client.get("/login?lang=ar", follow_redirects=False)
    assert response.status_code == 302 # Should redirect to strip lang param
    assert response.headers["location"] == "/login"
    assert "locale=ar" in response.headers["set-cookie"]

    # Follow the redirect, session should now be 'ar'
    response = client.get("/login", cookies={"locale": "ar"})
    assert response.status_code == 200
    assert "تسجيل الدخول إلى BookSlot" in response.text # Arabic translation

    response = client.get("/login?lang=fr", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/login"
    assert "locale=fr" in response.headers["set-cookie"]

    response = client.get("/login", cookies={"locale": "fr"})
    assert response.status_code == 200
    assert "Connexion à BookSlot" in response.text # French translation

    # Test default to English
    response = client.get("/login", cookies={"locale": "en"})
    assert response.status_code == 200
    assert "Login to BookSlot" in response.text

def test_i18n_dashboard_content(client: TestClient, db_session: TestingSessionLocal):
    owner_data = schemas.OwnerCreate(
        name="Test User", email="i18n@example.com", password="password",
        business_name="I18n Business", slug="i18n-biz", phone=None
    )
    owner = crud.create_owner(db_session, owner_data)
    client.post("/login", data={"email": "i18n@example.com", "password": "password"})

    # Check English dashboard
    response = client.get("/dashboard", cookies={"locale": "en"})
    assert response.status_code == 200
    assert "Welcome, Test User!" in response.text
    assert "Upcoming Bookings" in response.text

    # Check Arabic dashboard
    response = client.get("/dashboard", cookies={"locale": "ar"})
    assert response.status_code == 200
    assert "أهلاً بك، Test User!" in response.text
    assert "الحجوزات القادمة" in response.text

    # Check French dashboard
    response = client.get("/dashboard", cookies={"locale": "fr"})
    assert response.status_code == 200
    assert "Bienvenue, Test User!" in response.text
    assert "Prochaines réservations" in response.text

def test_health_check_endpoint(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
