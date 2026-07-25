import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import json
from datetime import date, timedelta, datetime

from src.main import app, get_db, get_current_owner, get_locale
from src.database import Base
from src import models, schemas, crud, security

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
    app.dependency_overrides = {} # Clear overrides after test

# Helper for authentication
def get_auth_client(client: TestClient, db_session: TestingSessionLocal, owner_email: str):
    owner = crud.get_owner_by_email(db_session, owner_email)
    if not owner:
        # Create a dummy owner for tests if needed
        owner_data = schemas.OwnerCreate(
            name="Test Owner",
            business_name="Test Business",
            email=owner_email,
            password="testpassword",
            slug="test-business"
        )
        owner = crud.create_owner(db_session, owner_data)

    access_token = security.create_access_token(data={"sub": owner.email})
    
    # Simulate session middleware setting the access_token
    # This is a bit tricky with TestClient, usually, you'd set cookies or headers
    # For now, we'll try to use a direct dependency override for get_current_owner
    # Alternatively, make the login endpoint directly callable and capture session.
    # For simplicity, let's create a client that always has this owner.

    def override_get_current_owner_for_test():
        return owner
    
    app.dependency_overrides[get_current_owner] = override_get_current_owner_for_test
    
    # Also, simulate session setup for the client
    with client as c:
        c.cookies["session"] = "mock_session_id" # Dummy session ID
        c.session.update({"access_token": access_token, "token_type": "bearer"})
        yield c
    app.dependency_overrides = {} # Clear overrides

# Test for health check
def test_health_check(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

# Test owner signup
def test_owner_signup(client: TestClient, db_session: TestingSessionLocal):
    response = client.post(
        "/signup",
        data={
            "name": "John Doe",
            "business_name": "JD Services",
            "email": "john@example.com",
            "password": "password123",
            "slug": "jd-services"
        },
        follow_redirects=False # Don't follow redirect to dashboard
    )
    assert response.status_code == 303 # Redirect to dashboard on successful signup
    assert response.headers["location"] == "/dashboard"

    owner = crud.get_owner_by_email(db_session, "john@example.com")
    assert owner is not None
    assert owner.name == "John Doe"
    assert security.verify_password("password123", owner.hashed_password)

def test_owner_signup_duplicate_email(client: TestClient, db_session: TestingSessionLocal):
    # First signup
    client.post(
        "/signup",
        data={
            "name": "John Doe",
            "business_name": "JD Services",
            "email": "duplicate@example.com",
            "password": "password123",
            "slug": "unique-slug"
        }
    )
    # Second signup with same email
    response = client.post(
        "/signup",
        data={
            "name": "Jane Doe",
            "business_name": "Jane Services",
            "email": "duplicate@example.com",
            "password": "password456",
            "slug": "another-unique-slug"
        }
    )
    assert response.status_code == 200 # Renders signup page with error
    assert "Email already registered" in response.text

def test_owner_signup_duplicate_slug(client: TestClient, db_session: TestingSessionLocal):
    # First signup
    client.post(
        "/signup",
        data={
            "name": "John Doe",
            "business_name": "JD Services",
            "email": "slug1@example.com",
            "password": "password123",
            "slug": "duplicate-slug"
        }
    )
    # Second signup with same slug
    response = client.post(
        "/signup",
        data={
            "name": "Jane Doe",
            "business_name": "Jane Services",
            "email": "slug2@example.com",
            "password": "password456",
            "slug": "duplicate-slug"
        }
    )
    assert response.status_code == 200 # Renders signup page with error
    assert "Business URL (slug) already taken" in response.text

# Test owner login
def test_owner_login(client: TestClient, db_session: TestingSessionLocal):
    # Create owner first
    owner_data = schemas.OwnerCreate(
        name="Login Test",
        business_name="Login Biz",
        email="login@example.com",
        password="testpassword",
        slug="login-biz"
    )
    crud.create_owner(db_session, owner_data)

    response = client.post(
        "/token",
        data={"username": "login@example.com", "password": "testpassword"},
        follow_redirects=False
    )
    assert response.status_code == 303 # Redirect to dashboard
    assert response.headers["location"] == "/dashboard"
    assert "access_token" in client.session # Check session for token

def test_owner_login_invalid_credentials(client: TestClient, db_session: TestingSessionLocal):
    response = client.post(
        "/token",
        data={"username": "nonexistent@example.com", "password": "wrongpassword"},
        follow_redirects=False
    )
    assert response.status_code == 303 # Redirect to login page
    assert response.headers["location"] == "/login"
    # To check flash message, would need to follow redirect and parse HTML,
    # or mock `flash` function. For now, status code and redirect suffice.

# Test dashboard access
def test_dashboard_requires_auth(client: TestClient):
    response = client.get("/dashboard", follow_redirects=False)
    assert response.status_code == 307 # Redirect to login (FastAPI's default for missing auth)
    assert response.headers["location"] == "/login"

def test_dashboard_access_authenticated(client: TestClient, db_session: TestingSessionLocal):
    # Create and login an owner
    owner_data = schemas.OwnerCreate(
        name="Dash Test",
        business_name="Dash Biz",
        email="dash@example.com",
        password="testpassword",
        slug="dash-biz"
    )
    crud.create_owner(db_session, owner_data)
    
    # Manually set session token for the test client
    access_token = security.create_access_token(data={"sub": "dash@example.com"})
    with client as c:
        c.cookies["session"] = "mock_session_id" # Dummy session ID
        c.session.update({"access_token": access_token, "token_type": "bearer"})
        response = c.get("/dashboard")
        assert response.status_code == 200
        assert "Welcome, Dash Test!" in response.text
        assert "Your Public Booking Page" in response.text

# Test profile update
def test_owner_profile_update(client: TestClient, db_session: TestingSessionLocal):
    # Create and login an owner
    owner_data = schemas.OwnerCreate(
        name="Profile Test",
        business_name="Profile Biz",
        email="profile@example.com",
        password="testpassword",
        slug="profile-biz"
    )
    owner = crud.create_owner(db_session, owner_data)

    access_token = security.create_access_token(data={"sub": owner.email})
    with client as c:
        c.cookies["session"] = "mock_session_id"
        c.session.update({"access_token": access_token, "token_type": "bearer"})

        updated_services = [
            {"name": "Haircut", "description": "Standard haircut", "duration_minutes": 30, "price": 25.0},
            {"name": "Shave", "description": "Classic shave", "duration_minutes": 15, "price": 15.0}
        ]
        updated_availability = [
            {"day_of_week": 0, "start_time": "09:00", "end_time": "17:00"},
            {"day_of_week": 1, "start_time": "10:00", "end_time": "18:00"}
        ]

        response = c.post(
            "/profile",
            data={
                "name": "Profile Updated",
                "business_name": "Updated Biz",
                "phone": "+1234567890",
                "services_json": json.dumps(updated_services),
                "availability_json": json.dumps(updated_availability)
            },
            follow_redirects=False
        )
        assert response.status_code == 303 # Redirect to profile page
        assert response.headers["location"] == "/profile"

        updated_owner = crud.get_owner(db_session, owner.id)
        assert updated_owner.name == "Profile Updated"
        assert updated_owner.business_name == "Updated Biz"
        assert updated_owner.phone == "+1234567890"
        assert json.loads(updated_owner.services_json) == updated_services
        assert json.loads(updated_owner.availability_json) == updated_availability

# Test public booking page
def test_public_booking_page_renders(client: TestClient, db_session: TestingSessionLocal):
    owner_data = schemas.OwnerCreate(
        name="Book Test",
        business_name="Book Biz",
        email="book@example.com",
        password="testpassword",
        slug="book-biz"
    )
    owner = crud.create_owner(db_session, owner_data)

    # Add some services and availability for the owner
    owner.services_json = json.dumps([
        {"name": "Service A", "description": "Desc A", "duration_minutes": 60, "price": 50.0}
    ])
    owner.availability_json = json.dumps([
        {"day_of_week": date.today().weekday(), "start_time": "09:00", "end_time": "17:00"}
    ])
    db_session.add(owner)
    db_session.commit()

    response = client.get("/book/book-biz")
    assert response.status_code == 200
    assert "Book Biz" in response.text
    assert "Service A" in response.text
    assert "Select Date" in response.text

def test_public_booking_page_not_found(client: TestClient):
    response = client.get("/book/non-existent-slug")
    assert response.status_code == 404
    assert "Owner not found" in response.text

# Test booking submission
def test_booking_submission(client: TestClient, db_session: TestingSessionLocal, mocker):
    owner_data = schemas.OwnerCreate(
        name="Booking Owner",
        business_name="Booking Co.",
        email="booking@example.com",
        password="testpassword",
        slug="booking-co",
        phone="+15005550006" # Twilio test number
    )
    owner = crud.create_owner(db_session, owner_data)

    # Add services and availability
    owner.services_json = json.dumps([
        {"name": "Consultation", "description": "Initial talk", "duration_minutes": 30, "price": 0.0}
    ])
    today_weekday = date.today().weekday() # Monday=0, Sunday=6
    owner.availability_json = json.dumps([
        {"day_of_week": today_weekday, "start_time": "09:00", "end_time": "17:00"}
    ])
    db_session.add(owner)
    db_session.commit()

    # Mock notification functions
    mocker.patch("src.notifications.send_email_notification", return_value=True)
    mocker.patch("src.notifications.send_whatsapp_notification", return_value=True)

    booking_date = date.today() + timedelta(days=1) # Book for tomorrow
    if booking_date.weekday() == 5: # If tomorrow is Saturday
        booking_date += timedelta(days=2) # Book for Monday
    elif booking_date.weekday() == 6: # If tomorrow is Sunday
        booking_date += timedelta(days=1) # Book for Monday

    response = client.post(
        "/book/booking-co",
        data={
            "customer_name": "Jane Customer",
            "customer_email": "jane@customer.com",
            "customer_phone": "+1234567890",
            "service_name": "Consultation",
            "booking_date": booking_date.strftime("%Y-%m-%d"),
            "booking_time": "10:00"
        },
        follow_redirects=False
    )
    assert response.status_code == 303 # Redirect to confirmation page
    assert response.headers["location"] == "/book/booking-co/confirmation"

    bookings = db_session.query(models.Booking).filter_by(owner_id=owner.id).all()
    assert len(bookings) == 1
    assert bookings[0].customer_email == "jane@customer.com"
    assert bookings[0].service_name == "Consultation"
    assert bookings[0].booking_date == booking_date
    assert bookings[0].booking_time == "10:00"

    # Verify notifications were called
    notifications.send_email_notification.assert_called()
    notifications.send_whatsapp_notification.assert_called()

def test_booking_submission_past_date(client: TestClient, db_session: TestingSessionLocal):
    owner_data = schemas.OwnerCreate(
        name="Past Date Owner",
        business_name="Past Date Co.",
        email="pastdate@example.com",
        password="testpassword",
        slug="past-date-co"
    )
    crud.create_owner(db_session, owner_data)

    response = client.post(
        "/book/past-date-co",
        data={
            "customer_name": "Test",
            "customer_email": "test@test.com",
            "service_name": "Service",
            "booking_date": (date.today() - timedelta(days=1)).strftime("%Y-%m-%d"),
            "booking_time": "10:00"
        },
        follow_redirects=False
    )
    assert response.status_code == 303 # Redirect back to booking page
    assert response.headers["location"] == "/book/past-date-co"
    # To properly check flash message "Cannot book a date in the past.", would need to follow redirect.

# Test for internationalization (i18n)
def test_language_toggle_on_login_page(client: TestClient):
    response = client.get("/login")
    assert "Login to your BookSlot account" in response.text # Default English

    # Test Arabic
    response = client.get("/login?lang=ar")
    assert "تسجيل الدخول إلى حسابك في بوك سلوت" in response.text

    # Test French
    response = client.get("/login?lang=fr")
    assert "Connectez-vous à votre compte BookSlot" in response.text

def test_language_toggle_on_booking_page(client: TestClient, db_session: TestingSessionLocal):
    owner_data = schemas.OwnerCreate(
        name="I18n Test",
        business_name="I18n Biz",
        email="i18n@example.com",
        password="testpassword",
        slug="i18n-biz"
    )
    crud.create_owner(db_session, owner_data)

    response = client.get("/book/i18n-biz")
    assert "Book your appointment with I18n Test." in response.text # Default English

    response = client.get("/book/i18n-biz?lang=ar")
    assert "احجز موعدك مع I18n Test." in response.text

    response = client.get("/book/i18n-biz?lang=fr")
    assert "Prenez rendez-vous avec I18n Test." in response.text

def test_language_toggle_on_dashboard_page(client: TestClient, db_session: TestingSessionLocal):
    owner_data = schemas.OwnerCreate(
        name="Dashboard I18n",
        business_name="Dashboard Biz",
        email="dash_i18n@example.com",
        password="testpassword",
        slug="dash-i18n"
    )
    owner = crud.create_owner(db_session, owner_data)
    access_token = security.create_access_token(data={"sub": owner.email})
    
    with client as c:
        c.cookies["session"] = "mock_session_id"
        c.session.update({"access_token": access_token, "token_type": "bearer"})
        
        response = c.get("/dashboard")
        assert "Welcome, Dashboard I18n!" in response.text # Default English

        c.session.update({"locale": "ar"}) # Simulate session locale change
        response = c.get("/dashboard?lang=ar") # Query param overrides session
        assert "مرحباً، Dashboard I18n!" in response.text

        c.session.update({"locale": "fr"})
        response = c.get("/dashboard?lang=fr")
        assert "Bienvenue, Dashboard I18n!" in response.text

# Test for error handling in profile update (invalid JSON)
def test_owner_profile_update_invalid_json(client: TestClient, db_session: TestingSessionLocal):
    owner_data = schemas.OwnerCreate(
        name="JSON Error Test",
        business_name="JSON Error Biz",
        email="jsonerror@example.com",
        password="testpassword",
        slug="json-error-biz"
    )
    owner = crud.create_owner(db_session, owner_data)

    access_token = security.create_access_token(data={"sub": owner.email})
    with client as c:
        c.cookies["session"] = "mock_session_id"
        c.session.update({"access_token": access_token, "token_type": "bearer"})

        response = c.post(
            "/profile",
            data={
                "name": "Updated Name",
                "business_name": "Updated Business",
                "phone": "+12345",
                "services_json": "NOT_VALID_JSON", # Invalid JSON
                "availability_json": "[]"
            },
            follow_redirects=False
        )
        assert response.status_code == 200 # Should re-render the profile page
        assert "Invalid JSON format for services or availability." in response.text

# Test for error handling in booking submission (invalid date format)
def test_booking_submission_invalid_date_format(client: TestClient, db_session: TestingSessionLocal):
    owner_data = schemas.OwnerCreate(
        name="Invalid Date Owner",
        business_name="Invalid Date Co.",
        email="invaliddate@example.com",
        password="testpassword",
        slug="invalid-date-co"
    )
    crud.create_owner(db_session, owner_data)

    response = client.post(
        "/book/invalid-date-co",
        data={
            "customer_name": "Test",
            "customer_email": "test@test.com",
            "service_name": "Service",
            "booking_date": "2023/10/27", # Invalid format
            "booking_time": "10:00"
        },
        follow_redirects=False
    )
    assert response.status_code == 303 # Redirect back to booking page
    assert response.headers["location"] == "/book/invalid-date-co"
    # To properly check flash message, would need to follow redirect and parse HTML.
