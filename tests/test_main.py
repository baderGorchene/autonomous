import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import json

# Import app and models from the main application
from src.main import app, get_db, get_templates_env
from src.database import Base, get_db as get_app_db
from src.models import Owner, Booking
from src import security
from src.config import settings
from src.i18n_config import get_jinja_templates

# Use an in-memory SQLite database for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"

# This is a temporary setup to ensure tests run. In a real scenario, use an in-memory db or a dedicated test db.
# The issue is that create_engine with check_same_thread=False is needed for SQLite but not for others.
# For testing, a fresh in-memory SQLite is best.
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(name="db_session")
def db_session_fixture():
    Base.metadata.create_all(bind=engine)  # Create tables
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine) # Drop tables after tests

@pytest.fixture(name="client")
def client_fixture(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    
    # Override the get_db dependency to use the test database session
    app.dependency_overrides[get_app_db] = override_get_db
    
    # Override get_templates_env to ensure a consistent English template for tests
    # or allow specific tests to override with other languages
    def override_get_templates_env(request):
        return get_jinja_templates('en') # Always use English for base tests
    app.dependency_overrides[get_templates_env] = override_get_templates_env

    with TestClient(app) as c:
        yield c

@pytest.fixture
def test_owner_data():
    return {
        "name": "Test Owner",
        "email": "test@example.com",
        "password": "testpassword",
        "business_name": "Test Business",
        "slug": "test-business",
        "phone": "+1234567890"
    }

@pytest.fixture
def auth_token(client, db_session, test_owner_data):
    # Create an owner first
    hashed_password = security.get_password_hash(test_owner_data["password"])
    owner = Owner(
        name=test_owner_data["name"],
        email=test_owner_data["email"],
        hashed_password=hashed_password,
        business_name=test_owner_data["business_name"],
        slug=test_owner_data["slug"],
        phone=test_owner_data["phone"],
        services_json=json.dumps([{"name": "Haircut", "duration_minutes": 60, "price": 50.0}]),
        availability_json=json.dumps({"0": [{"start_time": "09:00", "end_time": "17:00"}]})
    )
    db_session.add(owner)
    db_session.commit()
    db_session.refresh(owner)

    # Then log in to get a token
    response = client.post(
        "/login",
        data={
            "username": test_owner_data["email"],
            "password": test_owner_data["password"]
        }
    )
    assert response.status_code == 302 # Redirect to dashboard
    
    # Extract token from cookie
    cookies = client.cookies
    access_token_cookie = cookies.get("access_token")
    assert access_token_cookie is not None
    
    return access_token_cookie


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_signup_owner(client, db_session):
    # Test successful signup
    response = client.post(
        "/signup",
        data={
            "name": "New User",
            "email": "new@example.com",
            "password": "securepassword",
            "business_name": "New Business",
            "slug": "new-business-slug",
            "phone": "+1122334455"
        }
    )
    assert response.status_code == 302  # Redirect to login
    assert "/login" in response.headers["location"]
    owner = db_session.query(Owner).filter(Owner.email == "new@example.com").first()
    assert owner is not None
    assert owner.name == "New User"

    # Test signup with existing email
    response = client.post(
        "/signup",
        data={
            "name": "New User 2",
            "email": "new@example.com",
            "password": "securepassword2",
            "business_name": "Another Business",
            "slug": "another-business-slug",
            "phone": "+1122334456"
        }
    )
    assert response.status_code == 400
    assert "Email already registered" in response.text

    # Test signup with existing slug
    response = client.post(
        "/signup",
        data={
            "name": "New User 3",
            "email": "new3@example.com",
            "password": "securepassword3",
            "business_name": "Yet Another Business",
            "slug": "new-business-slug", # Duplicate slug
            "phone": "+1122334457"
        }
    )
    assert response.status_code == 400
    assert "Business link already taken" in response.text

def test_login_for_access_token(client, db_session, test_owner_data):
    # Create an owner first
    hashed_password = security.get_password_hash(test_owner_data["password"])
    owner = Owner(
        name=test_owner_data["name"],
        email=test_owner_data["email"],
        hashed_password=hashed_password,
        business_name=test_owner_data["business_name"],
        slug=test_owner_data["slug"],
        phone=test_owner_data["phone"]
    )
    db_session.add(owner)
    db_session.commit()

    # Test successful login
    response = client.post(
        "/login",
        data={
            "username": test_owner_data["email"],
            "password": test_owner_data["password"]
        }
    )
    assert response.status_code == 302 # Redirect to dashboard
    assert "/dashboard" in response.headers["location"]
    assert "access_token" in response.cookies

    # Test incorrect password
    response = client.post(
        "/login",
        data={
            "username": test_owner_data["email"],
            "password": "wrongpassword"
        }
    )
    assert response.status_code == 401
    assert "Incorrect email or password" in response.text

    # Test non-existent email
    response = client.post(
        "/login",
        data={
            "username": "nonexistent@example.com",
            "password": "anypassword"
        }
    )
    assert response.status_code == 401
    assert "Incorrect email or password" in response.text

def test_get_owner_dashboard(client, auth_token):
    response = client.get("/dashboard", cookies={"access_token": auth_token})
    assert response.status_code == 200
    assert "Welcome, Test Owner!" in response.text
    assert "Your Upcoming Bookings" in response.text

def test_update_owner_profile(client, db_session, auth_token, test_owner_data):
    # Fetch the owner to verify later
    initial_owner = db_session.query(Owner).filter(Owner.email == test_owner_data["email"]).first()
    assert initial_owner.name == "Test Owner"
    assert initial_owner.business_name == "Test Business"
    assert initial_owner.phone == "+1234567890"

    response = client.post(
        "/dashboard/profile",
        cookies={"access_token": auth_token},
        data={
            "name": "Updated Name",
            "business_name": "Updated Business",
            "phone": "+9876543210"
        }
    )
    assert response.status_code == 200
    assert "Profile updated successfully!" in response.text

    updated_owner = db_session.query(Owner).filter(Owner.email == test_owner_data["email"]).first()
    assert updated_owner.name == "Updated Name"
    assert updated_owner.business_name == "Updated Business"
    assert updated_owner.phone == "+9876543210"

def test_public_booking_page_display(client, db_session, test_owner_data):
    # Create an owner with services and availability
    hashed_password = security.get_password_hash(test_owner_data["password"])
    owner = Owner(
        name=test_owner_data["name"],
        email=test_owner_data["email"],
        hashed_password=hashed_password,
        business_name=test_owner_data["business_name"],
        slug=test_owner_data["slug"],
        phone=test_owner_data["phone"],
        services_json=json.dumps([{"name": "Consultation", "duration_minutes": 30, "price": 100.0}]),
        availability_json=json.dumps({"0": [{"start_time": "09:00", "end_time": "17:00"}]}) # Monday availability
    )
    db_session.add(owner)
    db_session.commit()
    db_session.refresh(owner)

    response = client.get(f"/{owner.slug}")
    assert response.status_code == 200
    assert owner.business_name in response.text
    assert "Select Service" in response.text
    assert "Consultation" in response.text
    assert "Available Time Slots" in response.text
    # Check for at least one time slot on Monday (day 0)
    today_weekday = datetime.now().weekday()
    if today_weekday == 0: # If today is Monday
        assert "09:00-10:00" in response.text

def test_submit_booking(client, db_session, test_owner_data):
    # Create an owner with services and availability
    hashed_password = security.get_password_hash(test_owner_data["password"])
    owner = Owner(
        name=test_owner_data["name"],
        email=test_owner_data["email"],
        hashed_password=hashed_password,
        business_name=test_owner_data["business_name"],
        slug=test_owner_data["slug"],
        phone=test_owner_data["phone"],
        services_json=json.dumps([{"name": "Massage", "duration_minutes": 60, "price": 75.0}]),
        availability_json=json.dumps({"0": [{"start_time": "09:00", "end_time": "17:00"}]}) # Monday availability
    )
    db_session.add(owner)
    db_session.commit()
    db_session.refresh(owner)

    booking_date = (date.today() + timedelta(days=(0 - date.today().weekday() + 7) % 7)).isoformat() # Next Monday

    response = client.post(
        f"/{owner.slug}/book",
        data={
            "customer_name": "Jane Doe",
            "customer_email": "jane@example.com",
            "customer_phone": "+1987654321",
            "service_name": "Massage",
            "booking_date": booking_date,
            "booking_time": "09:00-10:00"
        }
    )
    assert response.status_code == 200
    assert "Booking Confirmed!" in response.text
    assert "Jane Doe" in response.text
    assert "Massage" in response.text

    booking = db_session.query(Booking).filter(Booking.customer_email == "jane@example.com").first()
    assert booking is not None
    assert booking.owner_id == owner.id
    assert booking.service_name == "Massage"

def test_i18n_language_toggle(client, db_session, test_owner_data):
    # Create an owner
    hashed_password = security.get_password_hash(test_owner_data["password"])
    owner = Owner(
        name=test_owner_data["name"],
        email=test_owner_data["email"],
        hashed_password=hashed_password,
        business_name=test_owner_data["business_name"],
        slug=test_owner_data["slug"],
        phone=test_owner_data["phone"]
    )
    db_session.add(owner)
    db_session.commit()
    db_session.refresh(owner)

    # Test English (default)
    response_en = client.get(f"/{owner.slug}")
    assert response_en.status_code == 200
    assert "Select Service" in response_en.text # English translation

    # Test Arabic
    response_ar = client.get(f"/{owner.slug}?lang=ar")
    assert response_ar.status_code == 200 # Should redirect first, then get with cookie
    # Follow redirect
    redirected_response_ar = client.get(response_ar.headers["location"], cookies=response_ar.cookies)
    assert "اختر الخدمة" in redirected_response_ar.text # Arabic translation

    # Test French
    response_fr = client.get(f"/{owner.slug}?lang=fr")
    assert response_fr.status_code == 200 # Should redirect first
    # Follow redirect
    redirected_response_fr = client.get(response_fr.headers["location"], cookies=response_fr.cookies)
    assert "Sélectionner un Service" in redirected_response_fr.text # French translation

    # Verify language preference persists via session/cookie on dashboard
    # First login to get a valid token
    login_response = client.post(
        "/login",
        data={
            "username": test_owner_data["email"],
            "password": test_owner_data["password"]
        }
    )
    assert login_response.status_code == 302
    auth_token = login_response.cookies.get("access_token")

    # Access dashboard with French preference
    response_dashboard_fr = client.get("/dashboard?lang=fr", cookies={"access_token": auth_token})
    assert response_dashboard_fr.status_code == 200 # Should redirect first
    redirected_dashboard_fr = client.get(response_dashboard_fr.headers["location"], cookies=response_dashboard_fr.cookies)
    assert "Bienvenue," in redirected_dashboard_fr.text # French translation
    assert "Vos Prochaines Réservations" in redirected_dashboard_fr.text

    # Access dashboard with Arabic preference
    response_dashboard_ar = client.get("/dashboard?lang=ar", cookies={"access_token": auth_token})
    assert response_dashboard_ar.status_code == 200 # Should redirect first
    redirected_dashboard_ar = client.get(response_dashboard_ar.headers["location"], cookies=response_dashboard_ar.cookies)
    assert "أهلاً،" in redirected_dashboard_ar.text # Arabic translation
    assert "حجوزاتك القادمة" in redirected_dashboard_ar.text

