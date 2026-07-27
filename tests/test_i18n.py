import pytest
from fastapi.testclient import TestClient
from src.main import app
from src.config import settings
from unittest.mock import patch, MagicMock
import json
from src import crud, schemas, models

# Create a test client
client = TestClient(app)

# Mock SendGrid and Twilio to prevent actual external calls during tests
@pytest.fixture(autouse=True)
def mock_notifications():
    with patch('src.notifications.SendGridAPIClient') as mock_sendgrid, \
         patch('src.notifications.Client') as mock_twilio:
        yield mock_sendgrid, mock_twilio

# Override settings for testing (e.g., use an in-memory SQLite database)
@pytest.fixture(name="test_db")
def override_get_db_fixture():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from src.database import Base, get_db
    
    SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db" # Use a temporary test database
    engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    Base.metadata.create_all(bind=engine) # Create tables
    
    def get_test_db():
        try:
            db = TestingSessionLocal()
            yield db
        finally:
            db.close()
    
    app.dependency_overrides[get_db] = get_test_db # Override the dependency
    yield
    app.dependency_overrides.pop(get_db) # Clean up the override
    Base.metadata.drop_all(bind=engine) # Drop tables after tests

@pytest.fixture(name="auth_client")
def authenticated_client(test_db):
    # This fixture handles owner signup and login to provide an authenticated client
    db = next(app.dependency_overrides[app.dependency_overrides.get(lambda: None, lambda: None)]())
    existing_owner = db.query(models.Owner).filter(models.Owner.email == "test@example.com").first()
    if existing_owner:
        db.delete(existing_owner)
        db.commit()

    # Signup a test owner
    signup_response = client.post("/signup", data={
        "name": "Test Owner",
        "email": "test@example.com",
        "password": "testpassword",
        "business_name": "Test Business",
        "slug": "test-business",
        "phone": "+1234567890"
    }, follow_redirects=False)
    assert signup_response.status_code == 302 # Redirect to dashboard

    # Extract session cookie from signup response
    session_cookie = signup_response.cookies.get("session")
    assert session_cookie is not None

    # Use the session cookie for subsequent requests
    client.cookies.set("session", session_cookie)
    return client

def test_language_toggle_on_login_page():
    response = client.get("/login")
    assert response.status_code == 200
    assert "EN" in response.text
    assert "AR" in response.text
    assert "FR" in response.text

    # Test setting locale via /set_locale endpoint
    response = client.get("/set_locale/ar", follow_redirects=False)
    assert response.status_code == 302
    # The referer header isn't available in direct client.get, so it redirects to /
    # Let's assume it redirects to a page that will then use the session locale
    
    # Now request the login page again, it should use the 'ar' locale
    response = client.get("/login")
    assert response.status_code == 200
    assert "تسجيل الدخول إلى BookSlot" in response.text # Check for Arabic translation

    response = client.get("/set_locale/fr", follow_redirects=False)
    response = client.get("/login")
    assert response.status_code == 200
    assert "Connexion à BookSlot" in response.text # Check for French translation

def test_language_toggle_on_booking_page(test_db):
    # First, create an owner to have a booking page
    db = next(app.dependency_overrides[app.dependency_overrides.get(lambda: None, lambda: None)]())
    owner_in = schemas.OwnerCreate(
        name="Booking Page Owner",
        email="booking@example.com",
        password="securepassword",
        business_name="Booking Biz",
        slug="booking-biz",
        phone=None
    )
    crud.create_owner(db, owner_in)

    response = client.get("/bookslot/booking-biz")
    assert response.status_code == 200
    assert "EN" in response.text
    assert "AR" in response.text
    assert "FR" in response.text
    assert "Book an Appointment" in response.text # Default English

    # Set locale to Arabic and check booking page
    client.get("/set_locale/ar", follow_redirects=False)
    response = client.get("/bookslot/booking-biz")
    assert response.status_code == 200
    assert "احجز موعدا" in response.text # Arabic translation

    # Set locale to French and check booking page
    client.get("/set_locale/fr", follow_redirects=False)
    response = client.get("/bookslot/booking-biz")
    assert response.status_code == 200
    assert "Prendre un rendez-vous" in response.text # French translation

def test_language_toggle_on_dashboard(auth_client):
    # Ensure client is authenticated from auth_client fixture
    response = auth_client.get("/dashboard")
    assert response.status_code == 200
    assert "EN" in response.text
    assert "AR" in response.text
    assert "FR" in response.text
    assert "Dashboard" in response.text # Default English

    # Set locale to Arabic and check dashboard
    auth_client.get("/set_locale/ar", follow_redirects=False)
    response = auth_client.get("/dashboard")
    assert response.status_code == 200
    assert "لوحة التحكم" in response.text # Arabic translation

    # Set locale to French and check dashboard
    auth_client.get("/set_locale/fr", follow_redirects=False)
    response = auth_client.get("/dashboard")
    assert response.status_code == 200
    assert "Tableau de Bord" in response.text # French translation

def test_translation_of_dynamic_strings_in_booking_page_calendar(test_db):
    db = next(app.dependency_overrides[app.dependency_overrides.get(lambda: None, lambda: None)]())
    owner_in = schemas.OwnerCreate(
        name="Cal Owner",
        email="cal@example.com",
        password="securepassword",
        business_name="Cal Biz",
        slug="cal-biz",
        phone=None
    )
    db_owner = crud.create_owner(db, owner_in)
    
    # Update owner's services and availability so that calendar can render
    db_owner.services_json = json.dumps([{"name": "Haircut", "description": "Standard haircut", "duration_minutes": 30, "price": 25.0}])
    db_owner.availability_json = json.dumps({
        "Monday": [{"day_of_week": "Monday", "start_time": "09:00", "end_time": "17:00"}],
        "Tuesday": [{"day_of_week": "Tuesday", "start_time": "09:00", "end_time": "17:00"}]
    })
    db.add(db_owner)
    db.commit()
    db.refresh(db_owner)

    # Set locale to French
    client.get("/set_locale/fr", follow_redirects=False)
    response = client.get("/bookslot/cal-biz")
    assert response.status_code == 200
    assert "Lun" in response.text # Check for French short day name

    # Set locale to Arabic
    client.get("/set_locale/ar", follow_redirects=False)
    response = client.get("/bookslot/cal-biz")
    assert response.status_code == 200
    assert "الاثنين" in response.text # Check for Arabic full day name (or short if designed)
