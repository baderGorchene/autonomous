import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from datetime import datetime, timedelta
import json
from unittest.mock import patch
from fastapi.responses import Response
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

# Import models, schemas, main app, and database from src
from src.main import app, get_db, oauth2_scheme, get_current_owner, get_templates
from src import models, schemas, security, crud
from src.config import settings
from fastapi.templating import Jinja2Templates

# Override the database URL for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db" # Use in-memory SQLite for tests

@pytest.fixture(name="session")
def session_fixture():
    # Use StaticPool to ensure the same connection is used across threads,
    # which is important for SQLite in-memory databases with FastAPI's TestClient
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    models.Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        models.Base.metadata.drop_all(bind=engine) # Clean up after tests

@pytest.fixture(name="client")
def client_fixture(session: sessionmaker):
    def override_get_db():
        yield session
    app.dependency_overrides[get_db] = override_get_db
    
    from jinja2 import Environment, FileSystemLoader
    from jinja2.ext import i18n
    import gettext
    import os

    current_file_dir = os.path.dirname(os.path.abspath(__file__))
    PROJECT_ROOT = os.path.abspath(os.path.join(current_file_dir, os.pardir))
    TEMPLATES_DIR = os.path.join(PROJECT_ROOT, 'templates')

    def get_test_jinja_env(locale='en'):
        env = Environment(loader=FileSystemLoader(TEMPLATES_DIR), extensions=[i18n])
        translate = gettext.NullTranslations()
        env.install_gettext_translations(translate)
        def urlencode_query_param(url, query_param_name, value):
            parsed_url = urlparse(url)
            query_params = parse_qs(parsed_url.query)
            query_params[query_param_name] = [value]
            new_query = urlencode(query_params, doseq=True)
            return urlunparse(parsed_url._replace(query=new_query))
        env.filters['urlencode'] = urlencode_query_param
        return env

    def override_get_templates_for_test():
        class MockJinja2Templates(Jinja2Templates):
            def __init__(self, env):
                super().__init__(directory=TEMPLATES_DIR)
                self.env = env

            def TemplateResponse(self, name: str, context: dict, status_code: int = 200, headers: dict = None, media_type: str = "text/html"):
                template = self.env.get_template(name)
                return Response(template.render(context), status_code=status_code, headers=headers, media_type=media_type)

        return MockJinja2Templates(get_test_jinja_env())

    app.dependency_overrides[get_templates] = override_get_templates_for_test

    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear() # Clear overrides after test

@pytest.fixture
def owner_data():
    return {
        "name": "Test Owner",
        "email": "test@example.com",
        "password": "testpassword",
        "business_name": "Test Business",
        "slug": "test-business",
        "phone": "+1234567890"
    }

@pytest.fixture
def test_owner(session: sessionmaker, owner_data: dict):
    owner_in = schemas.OwnerCreate(**owner_data)
    owner = crud.create_owner(session, owner_in)
    return owner

@pytest.fixture
def authenticated_client(client: TestClient, test_owner: models.Owner, session: sessionmaker):
    response = client.post("/login", data={"username": test_owner.email, "password": "testpassword"})
    assert response.status_code == 302
    
    cookies = response.cookies
    access_token = cookies.get("access_token")
    assert access_token is not None

    def override_get_current_owner_mock():
        return test_owner
    app.dependency_overrides[get_current_owner] = override_get_current_owner_mock
    
    client.cookies.set("access_token", access_token)
    return client


# Mock notifications functions globally for all tests
@pytest.fixture(autouse=True)
def mock_notifications():
    with patch("src.notifications.send_email_notification") as mock_send_email, \
         patch("src.notifications.send_whatsapp_notification") as mock_send_whatsapp:
        yield mock_send_email, mock_send_whatsapp

# --- Tests ---

def test_health_check(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_signup_and_login(client: TestClient, owner_data: dict):
    response = client.get("/signup")
    assert response.status_code == 200
    assert "<h1>Owner Sign Up</h1>" in response.text

    response = client.post("/signup", data=owner_data)
    assert response.status_code == 302
    assert response.headers["location"] == "/login"

    response = client.get("/login")
    assert response.status_code == 200
    assert "<h1>Owner Login</h1>" in response.text

    response = client.post("/login", data={"username": owner_data["email"], "password": owner_data["password"]})
    assert response.status_code == 302
    assert response.headers["location"] == "/dashboard"
    assert "access_token" in response.cookies

def test_duplicate_signup_email(client: TestClient, test_owner: models.Owner, owner_data: dict):
    response = client.post("/signup", data=owner_data)
    assert response.status_code == 200
    assert "Email already registered" in response.text

def test_duplicate_signup_slug(client: TestClient, test_owner: models.Owner, owner_data: dict):
    owner_data_duplicate_slug = owner_data.copy()
    owner_data_duplicate_slug["email"] = "another@example.com"
    response = client.post("/signup", data=owner_data_duplicate_slug)
    assert response.status_code == 200
    assert "Booking page URL slug already taken" in response.text

def test_owner_dashboard_unauthenticated(client: TestClient):
    response = client.get("/dashboard")
    assert response.status_code == 302
    assert response.headers["location"] == "/login"

def test_owner_dashboard_authenticated(authenticated_client: TestClient, test_owner: models.Owner):
    response = authenticated_client.get("/dashboard")
    assert response.status_code == 200
    assert f"<h1>Welcome, {test_owner.name}!</h1>" in response.text
    assert f"Business Name: {test_owner.business_name}" in response.text
    assert "No upcoming bookings." in response.text

def test_update_owner_profile(authenticated_client: TestClient, test_owner: models.Owner, session: sessionmaker):
    new_name = "Updated Test Owner"
    new_business_name = "New Test Business"
    new_phone = "+9876543210"

    services_data = [
        {"name": "Haircut", "duration": 30, "price": 25.0, "description": "Standard haircut"},
        {"name": "Beard Trim", "duration": 15, "price": 10.0, "description": ""}
    ]
    availability_data = {
        "monday": [{"start_time": "09:00", "end_time": "17:00", "slot_duration": 30}],
        "tuesday": [{"start_time": "10:00", "end_time": "18:00", "slot_duration": 60}]
    }

    form_data = {
        "name": new_name,
        "business_name": new_business_name,
        "phone": new_phone,
        "service_name": [s["name"] for s in services_data],
        "service_duration": [str(s["duration"]) for s in services_data],
        "service_price": [str(s["price"]) for s in services_data],
        "service_description": [s["description"] for s in services_data],
        "availability_monday_start": [slot["start_time"] for slot in availability_data["monday"]],
        "availability_monday_end": [slot["end_time"] for slot in availability_data["monday"]],
        "availability_monday_slot_duration": [str(slot["slot_duration"]) for slot in availability_data["monday"]],
        "availability_tuesday_start": [slot["start_time"] for slot in availability_data["tuesday"]],
        "availability_tuesday_end": [slot["end_time"] for slot in availability_data["tuesday"]],
        "availability_tuesday_slot_duration": [str(slot["slot_duration"]) for slot in availability_data["tuesday"]],
    }

    response = authenticated_client.post("/owner/me", data=form_data)
    assert response.status_code == 200
    assert "Profile updated successfully!" in response.text

    updated_owner = crud.get_owner(session, test_owner.id)
    assert updated_owner.name == new_name
    assert updated_owner.business_name == new_business_name
    assert updated_owner.phone == new_phone
    assert json.loads(updated_owner.services_json) == [s for s in services_data]
    assert json.loads(updated_owner.availability_json) == availability_data

def test_public_booking_page_rendering(client: TestClient, test_owner: models.Owner, session: sessionmaker):
    services_data = [
        {"name": "Consultation", "duration": 60, "price": 50.0},
        {"name": "Follow-up", "duration": 30, "price": 30.0}
    ]
    test_owner.services_json = json.dumps(services_data)
    session.add(test_owner)
    session.commit()
    session.refresh(test_owner)

    response = client.get(f"/book/{test_owner.slug}")
    assert response.status_code == 200
    assert f"<h1>{test_owner.business_name}</h1>" in response.text
    assert "Consultation (60 min)" in response.text
    assert "Follow-up (30 min)" in response.text
    assert "Book Appointment" in response.text

def test_public_booking_page_not_found(client: TestClient):
    response = client.get("/book/non-existent-slug")
    assert response.status_code == 404
    assert response.json() == {"detail": "Owner not found"}

def test_booking_submission_success(client: TestClient, test_owner: models.Owner, session: sessionmaker, mock_notifications):
    services_data = [
        {"name": "Deep Cleaning", "duration": 90, "price": 100.0}
    ]
    test_owner.services_json = json.dumps(services_data)
    session.add(test_owner)
    session.commit()
    session.refresh(test_owner)

    booking_time = (datetime.now() + timedelta(days=1, hours=2)).replace(microsecond=0)
    booking_data = {
        "customer_name": "Jane Doe",
        "customer_email": "jane@example.com",
        "customer_phone": "+1122334455",
        "service_name": "Deep Cleaning",
        "booking_time": booking_time.isoformat()
    }

    response = client.post(f"/book/{test_owner.slug}", data=booking_data)
    assert response.status_code == 200
    assert "Booking Confirmed!" in response.text
    assert "A confirmation email has been sent to jane@example.com." in response.text

    bookings = session.query(models.Booking).filter(models.Booking.owner_id == test_owner.id).all()
    assert len(bookings) == 1
    assert bookings[0].customer_email == booking_data["customer_email"]
    assert bookings[0].service_name == booking_data["service_name"]
    assert bookings[0].booking_time == booking_time

    mock_send_email, mock_send_whatsapp = mock_notifications
    assert mock_send_email.call_count == 2
    assert mock_send_whatsapp.call_count == 2

def test_booking_submission_invalid_service(client: TestClient, test_owner: models.Owner, session: sessionmaker):
    services_data = [
        {"name": "Deep Cleaning", "duration": 90, "price": 100.0}
    ]
    test_owner.services_json = json.dumps(services_data)
    session.add(test_owner)
    session.commit()
    session.refresh(test_owner)

    booking_time = (datetime.now() + timedelta(days=1)).isoformat()
    booking_data = {
        "customer_name": "Jane Doe",
        "customer_email": "jane@example.com",
        "customer_phone": "+1122334455",
        "service_name": "Non-Existent Service",
        "booking_time": booking_time
    }

    response = client.post(f"/book/{test_owner.slug}", data=booking_data)
    assert response.status_code == 400
    assert "Invalid service selected." in response.text
    assert "Book Appointment" in response.text

def test_dashboard_shows_bookings(authenticated_client: TestClient, test_owner: models.Owner, session: sessionmaker):
    booking_time = datetime.now() + timedelta(hours=1)
    booking_data = schemas.BookingCreate(
        customer_name="Booked Customer",
        customer_email="booked@example.com",
        service_name="Test Service",
        booking_time=booking_time
    )
    crud.create_booking(session, booking_data, test_owner.id)

    response = authenticated_client.get("/dashboard")
    assert response.status_code == 200
    assert "Booked Customer" in response.text
    assert "Test Service" in response.text
    assert booking_time.strftime('%Y-%m-%d %H:%M') in response.text

def test_i18n_language_toggle_booking_page(client: TestClient, test_owner: models.Owner):
    response_en = client.get(f"/book/{test_owner.slug}?lang=en")
    assert response_en.status_code == 200
    assert "Book Now" in response_en.text
    
    response_ar = client.get(f"/book/{test_owner.slug}?lang=ar")
    assert response_ar.status_code == 200
    assert "احجز الآن" in response_ar.text
    
    response_fr = client.get(f"/book/{test_owner.slug}?lang=fr")
    assert response_fr.status_code == 200
    assert "Réserver maintenant" in response_fr.text

def test_i18n_language_toggle_dashboard_page(authenticated_client: TestClient, test_owner: models.Owner):
    response_en = authenticated_client.get("/dashboard?lang=en")
    assert response_en.status_code == 200
    assert "Upcoming Bookings" in response_en.text

    response_ar = authenticated_client.get("/dashboard?lang=ar")
    assert response_ar.status_code == 200
    assert "الحجوزات القادمة" in response_ar.text

    response_fr = authenticated_client.get("/dashboard?lang=fr")
    assert response_fr.status_code == 200
    assert "Réservations à venir" in response_fr.text

def test_error_handling_invalid_token(client: TestClient):
    client.cookies.set("access_token", "invalid.token.string")
    response = client.get("/dashboard")
    assert response.status_code == 302
    assert response.headers["location"] == "/login"

def test_logout(authenticated_client: TestClient):
    response = authenticated_client.get("/logout")
    assert response.status_code == 302
    assert response.headers["location"] == "/login"
    assert "access_token" not in response.cookies
