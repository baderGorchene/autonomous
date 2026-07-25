import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import json
from datetime import datetime, timedelta
import respx

from src.main import app, get_db, get_current_owner, oauth2_scheme
from src.database import Base
from src import models, security, crud, schemas, notifications
from src.config import settings

# Override settings for testing (e.g., mock API keys)
settings.SENDGRID_API_KEY = "test_sendgrid_key"
settings.TWILIO_ACCOUNT_SID = "ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
settings.TWILIO_AUTH_TOKEN = "your_auth_token"
settings.TWILIO_WHATSAPP_NUMBER = "+15005550006"
settings.SECRET_KEY = "test-secret-key"
settings.ACCESS_TOKEN_EXPIRE_MINUTES = 1

# Setup test database
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
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
    yield TestClient(app)
    app.dependency_overrides = {}

@pytest.fixture
def owner_data():
    return {
        "name": "Test Owner",
        "email": "test@example.com",
        "password": "testpassword",
        "business_name": "Test Business",
        "slug": "test-business"
    }

@pytest.fixture
def test_owner(db_session, owner_data):
    owner_create = schemas.OwnerCreate(**owner_data)
    return crud.create_owner(db_session, owner_create)

@pytest.fixture
def auth_token(test_owner):
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return security.create_access_token(
        data={"sub": test_owner.email},
        expires_delta=access_token_expires
    )

@pytest.fixture
def authorized_client(client, auth_token):
    client.cookies.set("access_token", auth_token)
    return client

# Mock external services
@pytest.fixture(autouse=True)
def mock_notifications(respx_mock):
    respx_mock.post("https://api.sendgrid.com/v3/mail/send").mock(return_value=respx.MockResponse(202))
    respx_mock.post("https://api.twilio.com/2010-04-01/Accounts/ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/Messages.json").mock(return_value=respx.MockResponse(201, json={"sid": "SMxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"}))

# --- Health Check ---
def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

# --- Owner Authentication & Profile ---
def test_signup(client, db_session, owner_data):
    response = client.post("/signup", data=owner_data)
    assert response.status_code == 302
    assert response.headers["location"] == "/dashboard"
    assert "access_token" in response.cookies
    owner = crud.get_owner_by_email(db_session, owner_data["email"])
    assert owner is not None
    assert owner.name == owner_data["name"]

def test_signup_email_exists(client, test_owner, owner_data):
    response = client.post("/signup", data=owner_data)
    assert response.status_code == 200 # Returns HTML with error
    assert "Email already registered" in response.text

def test_login(client, owner_data):
    response = client.post("/login", data={
        "email": owner_data["email"],
        "password": owner_data["password"]
    })
    assert response.status_code == 302
    assert response.headers["location"] == "/dashboard"
    assert "access_token" in response.cookies

def test_login_invalid_credentials(client, owner_data):
    response = client.post("/login", data={
        "email": owner_data["email"],
        "password": "wrongpassword"
    })
    assert response.status_code == 200 # Returns HTML with error
    assert "Incorrect email or password" in response.text

def test_dashboard_access(authorized_client):
    response = authorized_client.get("/dashboard")
    assert response.status_code == 200
    assert "Dashboard" in response.text

def test_dashboard_unauthorized(client):
    response = client.get("/dashboard")
    assert response.status_code == 302 # Redirects to /login
    assert response.headers["location"] == "/login"

def test_update_profile(authorized_client, test_owner, db_session):
    updated_name = "Updated Name"
    updated_business = "Updated Business Inc."
    updated_phone = "+1234567890"
    response = authorized_client.post("/profile", data={
        "name": updated_name,
        "business_name": updated_business,
        "phone": updated_phone
    })
    assert response.status_code == 200
    assert "Profile updated successfully!" in response.text
    db_session.refresh(test_owner)
    assert test_owner.name == updated_name
    assert test_owner.business_name == updated_business
    assert test_owner.phone == updated_phone

# --- Services and Availability ---
def test_update_services(authorized_client, test_owner, db_session):
    services_data = json.dumps([
        {"name": "Haircut", "description": "A professional haircut", "duration_minutes": 30, "price": 25.0},
        {"name": "Massage", "duration_minutes": 60, "price": 50.0}
    ])
    response = authorized_client.post("/services", data={"services_data": services_data})
    assert response.status_code == 200
    assert "Services updated successfully!" in response.text
    db_session.refresh(test_owner)
    assert json.loads(test_owner.services_json) == json.loads(services_data)

def test_update_availability(authorized_client, test_owner, db_session):
    availability_data = json.dumps({
        "0": [{"day_of_week": 0, "start_time": "09:00", "end_time": "17:00"}], # Monday
        "2": [{"day_of_week": 2, "start_time": "10:00", "end_time": "18:00"}]  # Wednesday
    })
    response = authorized_client.post("/availability", data={"availability_data": availability_data})
    assert response.status_code == 200
    assert "Availability updated successfully!" in response.text
    db_session.refresh(test_owner)
    assert json.loads(test_owner.availability_json) == json.loads(availability_data)

# --- Public Booking Page and Submission ---
def test_public_booking_page(client, test_owner):
    response = client.get(f"/{test_owner.slug}")
    assert response.status_code == 200
    assert test_owner.business_name in response.text
    assert "Book an Appointment" in response.text

def test_booking_submission(authorized_client, test_owner, db_session, mock_notifications):
    # First, set services and availability for the test_owner
    services_data = json.dumps([
        {"name": "Consultation", "description": "Initial talk", "duration_minutes": 30, "price": 0.0}
    ])
    test_owner.services_json = services_data
    db_session.add(test_owner)
    db_session.commit()
    db_session.refresh(test_owner)

    availability_data = json.dumps({
        str(datetime.now().weekday()): [{"day_of_week": datetime.now().weekday(), "start_time": "09:00", "end_time": "17:00"}]
    })
    test_owner.availability_json = availability_data
    db_session.add(test_owner)
    db_session.commit()
    db_session.refresh(test_owner)

    future_time = (datetime.now() + timedelta(days=1, hours=1)).replace(minute=0, second=0, microsecond=0) # Round to hour
    booking_data = {
        "customer_name": "Jane Doe",
        "customer_email": "jane@example.com",
        "customer_phone": "+1987654321",
        "service_name": "Consultation",
        "booking_date": future_time.strftime("%Y-%m-%d"),
        "booking_time": future_time.strftime("%H:%M")
    }
    response = authorized_client.post(f"/{test_owner.slug}/book", data=booking_data)
    assert response.status_code == 200
    assert "Booking successful!" in response.text
    
    bookings = db_session.query(models.Booking).filter(models.Booking.owner_id == test_owner.id).all()
    assert len(bookings) == 1
    assert bookings[0].customer_email == booking_data["customer_email"]
    assert bookings[0].service_name == booking_data["service_name"]
    assert respx_mock.calls.call_count == 4 # 2 emails, 2 whatsapp

def test_booking_submission_past_time_error(authorized_client, test_owner, db_session):
    # Set services and availability
    services_data = json.dumps([
        {"name": "Consultation", "description": "Initial talk", "duration_minutes": 30, "price": 0.0}
    ])
    test_owner.services_json = services_data
    db_session.add(test_owner)
    db_session.commit()
    db_session.refresh(test_owner)

    availability_data = json.dumps({
        str(datetime.now().weekday()): [{"day_of_week": datetime.now().weekday(), "start_time": "09:00", "end_time": "17:00"}]
    })
    test_owner.availability_json = availability_data
    db_session.add(test_owner)
    db_session.commit()
    db_session.refresh(test_owner)

    past_time = (datetime.now() - timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    booking_data = {
        "customer_name": "Jane Doe",
        "customer_email": "jane@example.com",
        "customer_phone": "+1987654321",
        "service_name": "Consultation",
        "booking_date": past_time.strftime("%Y-%m-%d"),
        "booking_time": past_time.strftime("%H:%M")
    }
    response = authorized_client.post(f"/{test_owner.slug}/book", data=booking_data)
    assert response.status_code == 200
    assert "Booking time must be in the future." in response.text

# --- Internationalization (i18n) ---
def test_language_toggle(client):
    # Default language (English)
    response = client.get("/login")
    assert response.status_code == 200
    assert "Login" in response.text

    # Set to Arabic
    response = client.post("/set-language", data={"lang": "ar"}, follow_redirects=False)
    assert response.status_code == 302
    assert "lang=ar" in response.headers["set-cookie"]

    # Request login page with Arabic cookie
    response = client.get("/login", cookies={"lang": "ar"})
    assert response.status_code == 200
    assert "تسجيل الدخول" in response.text # Arabic for 'Login'

    # Set to French
    response = client.post("/set-language", data={"lang": "fr"}, follow_redirects=False)
    assert response.status_code == 302
    assert "lang=fr" in response.headers["set-cookie"]

    # Request login page with French cookie
    response = client.get("/login", cookies={"lang": "fr"})
    assert response.status_code == 200
    assert "Connexion" in response.text # French for 'Login'
