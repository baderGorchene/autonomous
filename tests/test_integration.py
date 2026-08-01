import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.main import app, get_db, create_tables
from src.database import Base
from src.config import settings
from src import crud, schemas, security
import json
from datetime import datetime, date, timedelta

# Override settings for testing
settings.DATABASE_URL = "sqlite:///./test.db" # Use a file-based SQLite for clearer test isolation
settings.TESTING = True
settings.SECRET_KEY = "test_secret_key"
settings.ACCESS_TOKEN_EXPIRE_MINUTES = 1

# Setup test database
engine = create_engine(settings.DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="module")
def setup_db():
    Base.metadata.drop_all(bind=engine) # Start with a clean slate
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine) # Clean up after tests

@pytest.fixture(scope="function")
def db_session(setup_db):
    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)
    
    # Dependency override for tests
    def override_get_db():
        try:
            yield session
        finally:
            session.close()
    app.dependency_overrides[get_db] = override_get_db
    
    yield session
    
    session.close()
    transaction.rollback()
    connection.close()
    app.dependency_overrides = {} # Clear overrides

@pytest.fixture(scope="module")
def client():
    # Use TestClient for FastAPI app
    with TestClient(app) as c:
        yield c

# --- Test Cases ---

def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_signup_and_login(client, db_session):
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
    assert response.status_code == 302 # Redirect to dashboard after signup
    assert response.headers["location"] == "/dashboard"

    # Verify owner created in DB
    owner = crud.get_owner_by_email(db_session, email="test@example.com")
    assert owner is not None
    assert owner.name == "Test Owner"
    assert owner.business_name == "Test Business"
    assert owner.slug == "test-business"
    assert security.verify_password("testpassword", owner.hashed_password)

    # Test Login
    login_data = {
        "username": "test@example.com",
        "password": "testpassword"
    }
    response = client.post("/token", data=login_data)
    assert response.status_code == 302 # Redirect to dashboard
    assert response.headers["location"] == "/dashboard"
    
    # Check session cookie for token (or direct token if not redirecting)
    # The TestClient handles sessions automatically if SessionMiddleware is used.
    # We can check if the dashboard is accessible after login.
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert "Test Owner" in response.text
    assert "Test Business" in response.text

def test_signup_duplicate_email(client, db_session):
    signup_data = {
        "name": "Another Owner",
        "email": "duplicate@example.com",
        "password": "password123",
        "business_name": "Unique Business",
        "slug": "unique-business"
    }
    client.post("/signup", data=signup_data, follow_redirects=False) # First signup
    
    response = client.post("/signup", data=signup_data) # Duplicate signup
    assert response.status_code == 200 # Should re-render signup page with error
    assert "Email already registered" in response.text

def test_signup_duplicate_slug(client, db_session):
    signup_data_1 = {
        "name": "Owner One",
        "email": "owner1@example.com",
        "password": "password123",
        "business_name": "Biz One",
        "slug": "biz-slug"
    }
    client.post("/signup", data=signup_data_1, follow_redirects=False)

    signup_data_2 = {
        "name": "Owner Two",
        "email": "owner2@example.com",
        "password": "password123",
        "business_name": "Biz Two",
        "slug": "biz-slug" # Duplicate slug
    }
    response = client.post("/signup", data=signup_data_2)
    assert response.status_code == 200
    assert "Business URL already taken" in response.text

def test_dashboard_access_unauthenticated(client):
    response = client.get("/dashboard", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/login"

def test_owner_profile_update(client, db_session):
    # First, sign up and login
    signup_data = {
        "name": "Initial Owner",
        "email": "update@example.com",
        "password": "password",
        "business_name": "Initial Business",
        "slug": "initial-biz",
        "phone": "000"
    }
    client.post("/signup", data=signup_data, follow_redirects=False)
    client.post("/token", data={"username": "update@example.com", "password": "password"})

    # Get the current owner from DB to get initial state
    owner = crud.get_owner_by_email(db_session, email="update@example.com")
    assert owner.services_json == "[]"
    assert owner.availability_json == "{}"

    # Update profile
    updated_services = [{"name": "Massage", "duration": 60, "price": 50.0}]
    updated_availability = {"monday": [{"start": "09:00", "end": "17:00"}]}
    
    update_data = {
        "name": "Updated Owner Name",
        "business_name": "Updated Business Name",
        "phone": "+9876543210",
        "services_json": json.dumps(updated_services),
        "availability_json": json.dumps(updated_availability)
    }
    response = client.post("/dashboard/profile", data=update_data, follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/dashboard?success=profile_updated"

    # Verify update in DB
    updated_owner = crud.get_owner_by_email(db_session, email="update@example.com")
    assert updated_owner.name == "Updated Owner Name"
    assert updated_owner.business_name == "Updated Business Name"
    assert updated_owner.phone == "+9876543210"
    assert json.loads(updated_owner.services_json) == updated_services
    assert json.loads(updated_owner.availability_json) == updated_availability

def test_booking_page_display(client, db_session):
    # Setup an owner with services and availability
    owner = schemas.OwnerCreate(
        name="Booking Test Owner",
        email="bookme@example.com",
        password="password",
        business_name="Booking Clinic",
        slug="booking-clinic",
        phone="+1122334455"
    )
    db_owner = crud.create_owner(db_session, owner)
    
    services = [{"name": "Checkup", "duration": 30, "price": 75.0}, {"name": "Consultation", "duration": 60, "price": 100.0}]
    availability = {"monday": [{"start": "09:00", "end": "17:00"}], "tuesday": [{"start": "10:00", "end": "16:00"}]}
    
    db_owner.services_json = json.dumps(services)
    db_owner.availability_json = json.dumps(availability)
    db_session.add(db_owner)
    db_session.commit()
    db_session.refresh(db_owner)

    response = client.get("/bookslot/booking-clinic")
    assert response.status_code == 200
    assert "Booking Clinic" in response.text
    assert "Checkup" in response.text
    assert "Consultation" in response.text
    assert "9:00" in response.text # Availability might be rendered differently based on template

def test_booking_submission(client, db_session, mocker):
    # Mock notifications
    mocker.patch("src.notifications.send_email", return_value=True)
    mocker.patch("src.notifications.send_whatsapp_message", return_value=True)

    # Setup an owner with services and availability
    owner = schemas.OwnerCreate(
        name="Booking Submit Owner",
        email="submit@example.com",
        password="password",
        business_name="Submit Salon",
        slug="submit-salon",
        phone="+1987654321"
    )
    db_owner = crud.create_owner(db_session, owner)
    
    services = [{"name": "Haircut", "duration": 45, "price": 30.0}]
    availability = {
        (date.today() + timedelta(days=1)).strftime("%A").lower(): [{"start": "09:00", "end": "17:00"}]
    } # Ensure availability for tomorrow
    
    db_owner.services_json = json.dumps(services)
    db_owner.availability_json = json.dumps(availability)
    db_session.add(db_owner)
    db_session.commit()
    db_session.refresh(db_owner)

    booking_date_str = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")

    booking_data = {
        "customer_name": "Jane Doe",
        "customer_email": "jane@example.com",
        "customer_phone": "+15551234567",
        "service_name": "Haircut",
        "booking_date": booking_date_str,
        "booking_time": "10:00"
    }

    response = client.post("/bookslot/submit-salon/submit", data=booking_data)
    assert response.status_code == 200
    assert "Booking Confirmed!" in response.text
    assert "Jane Doe" in response.text
    assert "Haircut" in response.text

    # Verify booking in DB
    bookings = crud.get_owner_bookings(db_session, db_owner.id)
    assert len(bookings) == 1
    assert bookings[0].customer_email == "jane@example.com"
    assert bookings[0].service_name == "Haircut"
    assert bookings[0].booking_date.strftime("%Y-%m-%d") == booking_date_str
    assert bookings[0].booking_time == "10:00"
    
    # Verify notifications were called
    notifications.send_email.assert_called()
    notifications.send_whatsapp_message.assert_called()

def test_booking_submission_past_date_error(client, db_session):
    # Setup an owner (minimal)
    owner = schemas.OwnerCreate(
        name="Error Test Owner", email="error@example.com", password="password",
        business_name="Error Business", slug="error-biz"
    )
    db_owner = crud.create_owner(db_session, owner)
    
    # Update services and availability for the owner
    services = [{"name": "Consult", "duration": 30, "price": 50.0}]
    availability = {"monday": [{"start": "09:00", "end": "17:00"}]}
    db_owner.services_json = json.dumps(services)
    db_owner.availability_json = json.dumps(availability)
    db_session.add(db_owner)
    db_session.commit()
    db_session.refresh(db_owner)

    past_date_str = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    booking_data = {
        "customer_name": "Past Booker",
        "customer_email": "past@example.com",
        "service_name": "Consult",
        "booking_date": past_date_str,
        "booking_time": "10:00"
    }
    response = client.post("/bookslot/error-biz/submit", data=booking_data)
    assert response.status_code == 200 # Should re-render booking page with error
    assert "Cannot book in the past." in response.text

def test_language_toggle(client, db_session):
    # Test setting language to Arabic
    response = client.get("/set_language/ar", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/" # Redirects to root after setting lang
    
    # Check if a subsequent request for dashboard uses Arabic (example check)
    # First, sign up and login to get a session
    signup_data = {
        "name": "Lang Test Owner", "email": "lang@example.com", "password": "password",
        "business_name": "Lang Business", "slug": "lang-biz"
    }
    client.post("/signup", data=signup_data, follow_redirects=False)
    client.post("/token", data={"username": "lang@example.com", "password": "password"})

    # Now set language and try to access dashboard
    client.get("/set_language/ar", follow_redirects=False)
    response = client.get("/dashboard") # Should now render in Arabic
    
    # This assumes 'Dashboard' is translated in messages.po to Arabic.
    # For a real check, we'd need to know the Arabic string.
    # For now, we can check for a general indicator or assume the i18n config works.
    # Let's check the language toggle links on the page.
    response = client.get("/dashboard")
    assert 'href="/set_language/en"' in response.text
    assert 'href="/set_language/ar"' in response.text
    assert 'href="/set_language/fr"' in response.text

    # Test setting language to English
    response = client.get("/set_language/en", follow_redirects=False)
    assert response.status_code == 302
