import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from datetime import datetime, timedelta
import json

from src.main import app, get_db, oauth2_scheme, get_current_owner
from src.database import Base
from src import models, security, crud, schemas, notifications
from src.config import settings

settings.SENDGRID_API_KEY = "test_sendgrid_key"
settings.TWILIO_ACCOUNT_SID = "test_twilio_sid"
settings.TWILIO_AUTH_TOKEN = "test_twilio_token"
settings.TWILIO_WHATSAPP_NUMBER = "+15005550006"
settings.SECRET_KEY = "test-secret-key"
settings.ALGORITHM = "HS256"
settings.ACCESS_TOKEN_EXPIRE_MINUTES = 1

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
def client_fixture(db_session: TestingSessionLocal):
    def override_get_db():
        yield db_session
    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides = {}

def create_test_owner(db: TestingSessionLocal, email="test@example.com", password="password123", slug="test-business"):
    owner_create = schemas.OwnerCreate(
        name="Test Owner",
        email=email,
        password=password,
        business_name="Test Business",
        slug=slug,
        phone="+1234567890"
    )
    return crud.create_owner(db, owner_create)

def get_owner_token(client: TestClient, email, password):
    response = client.post(
        "/token",
        data={"username": email, "password": password}
    )
    assert response.status_code == 200
    return response.json()["access_token"]

def get_authenticated_client(client: TestClient, db_session: TestingSessionLocal, email="test@example.com", password="password123", slug="test-business"):
    owner = create_test_owner(db_session, email, password, slug)
    token = get_owner_token(client, email, password)
    client.headers = {"Authorization": f"Bearer {token}"}
    return client, owner

@pytest.fixture(autouse=True)
def mock_notifications(monkeypatch):
    monkeypatch.setattr(notifications, "send_booking_confirmation_email", lambda *args, **kwargs: None)
    monkeypatch.setattr(notifications, "send_whatsapp_notification", lambda *args, **kwargs: None)

def test_health_check(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_signup_page(client: TestClient):
    response = client.get("/signup")
    assert response.status_code == 200
    assert "Sign Up for BookSlot" in response.text

def test_signup_owner(client: TestClient, db_session: TestingSessionLocal):
    response = client.post(
        "/signup",
        data={
            "name": "New Owner",
            "email": "new@example.com",
            "password": "securepassword",
            "business_name": "New Biz",
            "slug": "new-biz",
            "phone": "+19876543210"
        },
        follow_redirects=False
    )
    assert response.status_code == 302
    assert response.headers["location"] == "/login"

    owner = crud.get_owner_by_email(db_session, "new@example.com")
    assert owner is not None
    assert owner.name == "New Owner"
    assert security.verify_password("securepassword", owner.hashed_password)

def test_signup_owner_duplicate_email(client: TestClient, db_session: TestingSessionLocal):
    create_test_owner(db_session)
    response = client.post(
        "/signup",
        data={
            "name": "Another Owner",
            "email": "test@example.com",
            "password": "password123",
            "business_name": "Another Biz",
            "slug": "another-biz"
        }
    )
    assert response.status_code == 200
    assert "Email already registered" in response.text

def test_signup_owner_duplicate_slug(client: TestClient, db_session: TestingSessionLocal):
    create_test_owner(db_session)
    response = client.post(
        "/signup",
        data={
            "name": "Another Owner",
            "email": "another@example.com",
            "password": "password123",
            "business_name": "Another Biz",
            "slug": "test-business"
        }
    )
    assert response.status_code == 200
    assert "Slug already taken" in response.text


def test_login_page(client: TestClient):
    response = client.get("/login")
    assert response.status_code == 200
    assert "Login to BookSlot" in response.text

def test_login_owner_success(client: TestClient, db_session: TestingSessionLocal):
    create_test_owner(db_session)
    response = client.post(
        "/login",
        data={"email": "test@example.com", "password": "password123"},
        follow_redirects=False
    )
    assert response.status_code == 302
    assert response.headers["location"] == "/dashboard"
    assert "access_token" in response.cookies

def test_login_owner_invalid_credentials(client: TestClient, db_session: TestingSessionLocal):
    create_test_owner(db_session)
    response = client.post(
        "/login",
        data={"email": "test@example.com", "password": "wrongpassword"}
    )
    assert response.status_code == 401
    assert "Incorrect email or password" in response.text

def test_dashboard_access(client: TestClient, db_session: TestingSessionLocal):
    auth_client, owner = get_authenticated_client(client, db_session)
    response = auth_client.get("/dashboard")
    assert response.status_code == 200
    assert f"Welcome, {owner.name}!" in response.text
    assert f"bookslot.app/{owner.slug}" in response.text

def test_dashboard_unauthorized_access(client: TestClient):
    response = client.get("/dashboard")
    assert response.status_code == 401
    assert "Not authenticated" in response.text

def test_update_owner_profile(client: TestClient, db_session: TestingSessionLocal):
    auth_client, owner = get_authenticated_client(client, db_session)

    new_services = [
        {"name": "Haircut", "duration_minutes": 30, "price": 25.0},
        {"name": "Coloring", "duration_minutes": 90, "price": 80.0}
    ]
    new_availability = {
        "monday": {"is_available": True, "slots": [{"start_time": "09:00", "end_time": "17:00"}]},
        "tuesday": {"is_available": False, "slots": []}
    }

    response = auth_client.post(
        "/dashboard/update_profile",
        data={
            "name": "Updated Name",
            "business_name": "Updated Business",
            "phone": "+1122334455",
            "services_json": json.dumps(new_services),
            "availability_json": json.dumps(new_availability)
        }
    )
    assert response.status_code == 200
    assert "Profile updated successfully!" in response.text

    updated_owner = crud.get_owner(db_session, owner.id)
    assert updated_owner.name == "Updated Name"
    assert updated_owner.business_name == "Updated Business"
    assert updated_owner.phone == "+1122334455"
    assert json.loads(updated_owner.services_json) == new_services
    assert json.loads(updated_owner.availability_json) == new_availability

def test_public_booking_page(client: TestClient, db_session: TestingSessionLocal):
    owner = create_test_owner(db_session)
    response = client.get(f"/bookslot.app/{owner.slug}")
    assert response.status_code == 200
    assert f"Book with {owner.business_name}" in response.text
    assert "Select Service and Time" in response.text

def test_public_booking_page_not_found(client: TestClient):
    response = client.get("/bookslot.app/non-existent-slug")
    assert response.status_code == 404
    assert "Owner not found" in response.json()["detail"]

def test_submit_booking_success(client: TestClient, db_session: TestingSessionLocal):
    owner = create_test_owner(db_session)
    owner.services_json = json.dumps([{"name": "Consultation", "duration_minutes": 60, "price": 50.0}])
    owner.availability_json = json.dumps({
        "monday": {"is_available": True, "slots": [{"start_time": "09:00", "end_time": "17:00"}]}
    })
    db_session.add(owner)
    db_session.commit()
    db_session.refresh(owner)

    booking_time = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d %H:%M").split(" ")
    booking_date = booking_time[0]
    booking_hour_minute = booking_time[1]
    
    response = client.post(
        f"/bookslot.app/{owner.slug}/book",
        data={
            "customer_name": "Jane Doe",
            "customer_email": "jane@example.com",
            "customer_phone": "+1234567890",
            "service_name": "Consultation",
            "booking_date": booking_date,
            "booking_time": booking_hour_minute
        },
        follow_redirects=False
    )
    assert response.status_code == 302
    assert response.headers["location"] == f"/bookslot.app/{owner.slug}/confirmation"

    bookings = db_session.query(models.Booking).filter(models.Booking.owner_id == owner.id).all()
    assert len(bookings) == 1
    assert bookings[0].customer_email == "jane@example.com"
    assert bookings[0].service_name == "Consultation"

def test_submit_booking_invalid_time(client: TestClient, db_session: TestingSessionLocal):
    owner = create_test_owner(db_session)
    owner.services_json = json.dumps([{"name": "Consultation", "duration_minutes": 60, "price": 50.0}])
    owner.availability_json = json.dumps({
        "monday": {"is_available": True, "slots": [{"start_time": "09:00", "end_time": "17:00"}]}
    })
    db_session.add(owner)
    db_session.commit()
    db_session.refresh(owner)

    past_time = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M").split(" ")
    past_date = past_time[0]
    past_hour_minute = past_time[1]

    response = client.post(
        f"/bookslot.app/{owner.slug}/book",
        data={
            "customer_name": "Jane Doe",
            "customer_email": "jane@example.com",
            "customer_phone": "+1234567890",
            "service_name": "Consultation",
            "booking_date": past_date,
            "booking_time": past_hour_minute
        }
    )
    assert response.status_code == 400
    assert "Booking time must be in the future." in response.text

def test_booking_confirmation_page(client: TestClient, db_session: TestingSessionLocal):
    owner = create_test_owner(db_session)
    response = client.get(f"/bookslot.app/{owner.slug}/confirmation")
    assert response.status_code == 200
    assert "Booking Confirmed!" in response.text
    assert f"Thank you for your booking with {owner.business_name}." in response.text

def test_language_toggle_on_dashboard(client: TestClient, db_session: TestingSessionLocal):
    auth_client, owner = get_authenticated_client(client, db_session)

    response = auth_client.post("/set-locale", data={"locale": "ar"}, follow_redirects=False)
    assert response.status_code == 302
    assert response.cookies["locale"] == "ar"

    response = auth_client.get("/dashboard", cookies={"locale": "ar"})
    assert response.status_code == 200
    assert "أهلاً بك،" in response.text

    response = auth_client.post("/set-locale", data={"locale": "fr"}, follow_redirects=False)
    assert response.status_code == 302
    assert response.cookies["locale"] == "fr"

    response = auth_client.get("/dashboard", cookies={"locale": "fr"})
    assert response.status_code == 200
    assert "Bienvenue," in response.text

    response = auth_client.post("/set-locale", data={"locale": "en"}, follow_redirects=False)
    assert response.status_code == 302
    assert response.cookies["locale"] == "en"

    response = auth_client.get("/dashboard", cookies={"locale": "en"})
    assert response.status_code == 200
    assert "Welcome," in response.text

def test_language_toggle_on_booking_page(client: TestClient, db_session: TestingSessionLocal):
    owner = create_test_owner(db_session)

    response = client.post("/set-locale", data={"locale": "ar"}, headers={"Referer": f"/bookslot.app/{owner.slug}"}, follow_redirects=False)
    assert response.status_code == 302
    assert response.cookies["locale"] == "ar"

    response = client.get(f"/bookslot.app/{owner.slug}", cookies={"locale": "ar"})
    assert response.status_code == 200
    assert "احجز مع" in response.text

    response = client.post("/set-locale", data={"locale": "fr"}, headers={"Referer": f"/bookslot.app/{owner.slug}"}, follow_redirects=False)
    assert response.status_code == 302
    assert response.cookies["locale"] == "fr"

    response = client.get(f"/bookslot.app/{owner.slug}", cookies={"locale": "fr"})
    assert response.status_code == 200
    assert "Réserver avec" in response.text
