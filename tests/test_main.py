import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import os
from datetime import date, timedelta
import json

# Import the main application and database components
from src.main import app, get_db
from src.database import Base
from src.config import settings
from src import models, schemas, crud, security

# Override settings for testing
settings.DATABASE_URL = "sqlite:///./test.db"
settings.SECRET_KEY = "super-secret-test-key"
settings.ALGORITHM = "HS256"
settings.ACCESS_TOKEN_EXPIRE_MINUTES = 1

# Setup test database
engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)

@pytest.fixture(name="db_session")
def db_session_fixture():
    """Provides a transactional test database session."""
    Base.metadata.drop_all(bind=engine) # Start fresh for each test
    Base.metadata.create_all(bind=engine)
    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()

@pytest.fixture(name="client")
def client_fixture(db_session: TestingSessionLocal):
    """Provides a test client for the FastAPI app."""
    def override_get_db():
        try:
            yield db_session
        finally:
            db_session.close() # This close is important for the fixture cleanup

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()

@pytest.fixture
def test_owner_data():
    return {
        "name": "Test Owner",
        "email": "test@example.com",
        "password": "testpassword",
        "business_name": "Test Business",
        "slug": "test-business",
        "phone": "+15551234567",
    }

@pytest.fixture
def create_test_owner(db_session: TestingSessionLocal, test_owner_data):
    owner_in = schemas.OwnerCreate(**test_owner_data)
    owner = crud.create_owner(db_session, owner_in)
    db_session.refresh(owner)
    return owner

@pytest.fixture
def owner_token(client: TestClient, test_owner_data):
    response = client.post(
        "/token",
        data={"username": test_owner_data["email"], "password": test_owner_data["password"]}
    )
    assert response.status_code == 200
    return response.json()["access_token"]

# --- Tests ---

def test_health_check(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_signup_page(client: TestClient):
    response = client.get("/signup")
    assert response.status_code == 200
    assert "Create your BookSlot account" in response.text

def test_owner_signup_success(client: TestClient, db_session: TestingSessionLocal, test_owner_data):
    response = client.post(
        "/signup",
        data=test_owner_data,
        follow_redirects=False # Important to check redirect status
    )
    assert response.status_code == 303 # Redirect to login
    assert response.headers["location"] == "/login"

    owner = crud.get_owner_by_email(db_session, test_owner_data["email"])
    assert owner is not None
    assert owner.name == test_owner_data["name"]
    assert security.verify_password(test_owner_data["password"], owner.hashed_password)

def test_owner_signup_duplicate_email(client: TestClient, create_test_owner, test_owner_data):
    response = client.post(
        "/signup",
        data=test_owner_data,
        follow_redirects=False
    )
    assert response.status_code == 303 # Redirect back to signup
    assert response.headers["location"] == "/signup"
    # Flash message check would require session inspection, which TestClient doesn't directly expose easily.

def test_owner_signup_duplicate_slug(client: TestClient, create_test_owner, test_owner_data):
    # Create another owner with a different email but same slug
    new_owner_data = test_owner_data.copy()
    new_owner_data["email"] = "another@example.com"
    response = client.post(
        "/signup",
        data=new_owner_data,
        follow_redirects=False
    )
    assert response.status_code == 303 # Redirect back to signup
    assert response.headers["location"] == "/signup"

def test_login_page(client: TestClient):
    response = client.get("/login")
    assert response.status_code == 200
    assert "Login to your BookSlot account" in response.text

def test_owner_login_success(client: TestClient, create_test_owner, test_owner_data):
    response = client.post(
        "/login",
        data={"email": test_owner_data["email"], "password": test_owner_data["password"]},
        follow_redirects=False
    )
    assert response.status_code == 303 # Redirect to dashboard
    assert response.headers["location"] == "/dashboard"
    assert "access_token" in response.cookies

def test_owner_login_invalid_credentials(client: TestClient, create_test_owner, test_owner_data):
    response = client.post(
        "/login",
        data={"email": test_owner_data["email"], "password": "wrongpassword"},
        follow_redirects=False
    )
    assert response.status_code == 303 # Redirect back to login
    assert response.headers["location"] == "/login"

def test_dashboard_access_authenticated(client: TestClient, owner_token):
    response = client.get(
        "/dashboard",
        cookies={"access_token": owner_token}
    )
    assert response.status_code == 200
    assert "Welcome, Test Owner!" in response.text

def test_dashboard_access_unauthenticated(client: TestClient):
    response = client.get("/dashboard", follow_redirects=False)
    assert response.status_code == 307 # Redirect to login (or 401 if direct API)

def test_profile_page_access_authenticated(client: TestClient, owner_token):
    response = client.get(
        "/profile",
        cookies={"access_token": owner_token}
    )
    assert response.status_code == 200
    assert "Manage Your Profile & Services" in response.text

def test_update_profile_success(client: TestClient, db_session: TestingSessionLocal, create_test_owner, owner_token):
    updated_name = "Updated Test Owner"
    updated_business_name = "Updated Business Name"
    updated_phone = "+1234567890"
    services_data = json.dumps([
        {"name": "Haircut", "description": "Standard haircut", "duration_minutes": 30, "price": 25.0},
        {"name": "Shave", "duration_minutes": 15}
    ])
    availability_data = json.dumps({
        "Monday": [{"start_time": "09:00", "end_time": "17:00"}],
        "Tuesday": [{"start_time": "10:00", "end_time": "18:00"}]
    })

    response = client.post(
        "/profile",
        data={
            "name": updated_name,
            "business_name": updated_business_name,
            "phone": updated_phone,
            "services_json": services_data,
            "availability_json": availability_data
        },
        cookies={"access_token": owner_token},
        follow_redirects=False
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/profile"

    owner = crud.get_owner_by_email(db_session, create_test_owner.email)
    assert owner.name == updated_name
    assert owner.business_name == updated_business_name
    assert owner.phone == updated_phone
    assert owner.services_json == services_data
    assert owner.availability_json == availability_data

def test_public_booking_page_exists(client: TestClient, create_test_owner):
    response = client.get(f"/bookslot/{create_test_owner.slug}")
    assert response.status_code == 200
    assert f"Book Your Appointment with {create_test_owner.business_name}" in response.text

def test_public_booking_page_not_found(client: TestClient):
    response = client.get("/bookslot/non-existent-slug")
    assert response.status_code == 404
    assert "Booking page not found" in response.text

def test_submit_booking_success(client: TestClient, db_session: TestingSessionLocal, create_test_owner):
    # Update owner's services and availability first
    services_data = json.dumps([
        {"name": "Consultation", "duration_minutes": 60, "price": 50.0},
        {"name": "Quick Chat", "duration_minutes": 30}
    ])
    availability_data = json.dumps({
        date.today().strftime('%A'): [{"start_time": "09:00", "end_time": "17:00"}]
    })
    create_test_owner.services_json = services_data
    create_test_owner.availability_json = availability_data
    db_session.add(create_test_owner)
    db_session.commit()
    db_session.refresh(create_test_owner)

    booking_data = {
        "customer_name": "Jane Doe",
        "customer_email": "jane@example.com",
        "customer_phone": "+1234567890",
        "service_name": "Consultation",
        "booking_date": date.today().isoformat(),
        "booking_time": "10:00 AM"
    }

    response = client.post(
        f"/bookslot/{create_test_owner.slug}",
        data=booking_data
    )
    assert response.status_code == 200
    assert "Booking Confirmed!" in response.text

    booking = db_session.query(models.Booking).filter_by(customer_email="jane@example.com").first()
    assert booking is not None
    assert booking.service_name == "Consultation"
    assert booking.owner_id == create_test_owner.id

def test_submit_booking_missing_fields(client: TestClient, create_test_owner):
    booking_data = {
        "customer_name": "Jane Doe",
        "customer_email": "jane@example.com",
        # "service_name": "Consultation", # Missing
        "booking_date": date.today().isoformat(),
        "booking_time": "10:00 AM"
    }
    response = client.post(
        f"/bookslot/{create_test_owner.slug}",
        data=booking_data
    )
    assert response.status_code == 200 # Renders booking page again with error
    assert "All required fields must be filled." in response.text

def test_language_toggle(client: TestClient):
    # Test setting language to Arabic
    response = client.get("/lang/ar", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/" # Redirects to root by default

    # Now request root page and check if Arabic is used
    response = client.get("/", cookies={"session": response.cookies["session"]})
    assert response.status_code == 200
    assert "مرحباً بكم في بوك سلوت" in response.text # Check for Arabic translation

    # Test setting language to French
    response = client.get("/lang/fr", follow_redirects=False)
    assert response.status_code == 303
    response = client.get("/", cookies={"session": response.cookies["session"]})
    assert response.status_code == 200
    assert "Bienvenue sur BookSlot" in response.text # Check for French translation