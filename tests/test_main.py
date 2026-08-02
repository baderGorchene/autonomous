import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.main import app, get_db
from src.database import Base, create_tables, drop_tables
from src.config import settings
from src import crud, models, security, schemas
import json
import datetime
from unittest.mock import patch

# Setup for in-memory SQLite database
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="module", autouse=True)
def setup_test_environment():
    original_testing_setting = settings.TESTING
    original_database_url = settings.DATABASE_URL
    settings.TESTING = True
    settings.DATABASE_URL = SQLALCHEMY_DATABASE_URL
    
    create_tables()
    yield
    
drop_tables()
    settings.TESTING = original_testing_setting
    settings.DATABASE_URL = original_database_url

@pytest.fixture(name="db_session")
def db_session_fixture():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

@pytest.fixture(name="client")
def client_fixture(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()

def create_test_owner_and_get_token(client, db_session, email="test@example.com", password="testpassword", slug="testbiz"):
    owner_data = schemas.OwnerCreate(
        name="Test Owner",
        email=email,
        password=password,
        business_name="Test Business",
        slug=slug,
        phone="+1234567890"
    )
    crud.create_owner(db_session, owner_data)
    
    response = client.post(
        "/token",
        data={"username": email, "password": password}
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    return token, owner_data.slug

def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_signup_page(client):
    response = client.get("/signup")
    assert response.status_code == 200
    assert "Create Your BookSlot Account" in response.text

def test_post_signup_success(client, db_session):
    response = client.post(
        "/signup",
        data={
            "name": "New Owner",
            "email": "new@example.com",
            "password": "newpassword",
            "business_name": "New Business",
            "slug": "newbiz",
            "phone": "+19876543210"
        },
        follow_redirects=False
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/login"
    owner = crud.get_owner_by_email(db_session, "new@example.com")
    assert owner is not None
    assert owner.name == "New Owner"

def test_post_signup_duplicate_email(client, db_session):
    create_test_owner_and_get_token(client, db_session, email="dup@example.com", slug="dup")
    response = client.post(
        "/signup",
        data={
            "name": "Dup Owner",
            "email": "dup@example.com",
            "password": "password",
            "business_name": "Dup Business",
            "slug": "anotherdup"
        }
    )
    assert response.status_code == 400
    assert "Email already registered" in response.text

def test_post_signup_duplicate_slug(client, db_session):
    create_test_owner_and_get_token(client, db_session, email="slugtest@example.com", slug="existing-slug")
    response = client.post(
        "/signup",
        data={
            "name": "Slug Owner",
            "email": "another@example.com",
            "password": "password",
            "business_name": "Slug Business",
            "slug": "existing-slug"
        }
    )
    assert response.status_code == 400
    assert "Business URL already taken" in response.text

def test_login_page(client):
    response = client.get("/login")
    assert response.status_code == 200
    assert "Login to Your Account" in response.text

def test_post_login_success(client, db_session):
    token, _ = create_test_owner_and_get_token(client, db_session, email="login@example.com", slug="loginbiz")
    response = client.post(
        "/login",
        data={"email": "login@example.com", "password": "testpassword"},
        follow_redirects=False
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/dashboard"
    assert "access_token" in response.cookies

def test_post_login_invalid_credentials(client, db_session):
    create_test_owner_and_get_token(client, db_session, email="badlogin@example.com", slug="badloginbiz")
    response = client.post(
        "/login",
        data={"email": "badlogin@example.com", "password": "wrongpassword"}
    )
    assert response.status_code == 401
    assert "Incorrect email or password" in response.text

def test_logout(client, db_session):
    token, _ = create_test_owner_and_get_token(client, db_session)
    response = client.get("/logout", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"
    assert "access_token" not in response.cookies

def test_dashboard_access_unauthenticated(client):
    response = client.get("/dashboard", follow_redirects=False)
    assert response.status_code == 307

def test_dashboard_access_authenticated(client, db_session):
    token, _ = create_test_owner_and_get_token(client, db_session, email="dash@example.com", slug="dashbiz")
    response = client.get(
        "/dashboard",
        cookies={"access_token": f"Bearer {token}"}
    )
    assert response.status_code == 200
    assert "Welcome, Test Owner!" in response.text
    assert "Upcoming Bookings" in response.text

def test_update_profile_success(client, db_session):
    token, _ = create_test_owner_and_get_token(client, db_session, email="update@example.com", slug="updatebiz")
    
    owner = crud.get_owner_by_email(db_session, "update@example.com")
    assert owner.name == "Test Owner"
    assert owner.business_name == "Test Business"
    assert owner.phone == "+1234567890"
    assert json.loads(owner.services_json) == []
    assert json.loads(owner.availability_json) == {}

    updated_services = [
        {"name": "Haircut", "duration": 60, "price": 50.0, "description": "Standard haircut"},
        {"name": "Shave", "duration": 30, "price": 25.0, "description": None}
    ]
    updated_availability = [
        {"day_of_week": 0, "start_time": "09:00", "end_time": "17:00"},
        {"day_of_week": 1, "start_time": "10:00", "end_time": "18:00"}
    ]

    response = client.post(
        "/dashboard/profile",
        data={
            "name": "Updated Owner",
            "business_name": "Updated Business Inc.",
            "phone": "+1122334455",
            "services_json": json.dumps(updated_services),
            "availability_json": json.dumps(updated_availability)
        },
        cookies={"access_token": f"Bearer {token}"},
        follow_redirects=False
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/dashboard?success=true"

    owner = crud.get_owner_by_email(db_session, "update@example.com")
    assert owner.name == "Updated Owner"
    assert owner.business_name == "Updated Business Inc."
    assert owner.phone == "+1122334455"
    assert json.loads(owner.services_json) == updated_services
    assert json.loads(owner.availability_json) == updated_availability

def test_update_profile_invalid_json(client, db_session):
    token, _ = create_test_owner_and_get_token(client, db_session, email="invalidjson@example.com", slug="invalidjsonbiz")
    response = client.post(
        "/dashboard/profile",
        data={
            "name": "Owner",
            "business_name": "Business",
            "services_json": "invalid json",
            "availability_json": "{}"
        },
        cookies={"access_token": f"Bearer {token}"}
    )
    assert response.status_code == 400
    assert "Invalid JSON format for services or availability." in response.text

def test_public_booking_page_not_found(client):
    response = client.get("/nonexistent-slug")
    assert response.status_code == 404
    assert "Owner not found." in response.text

def test_public_booking_page_success(client, db_session):
    token, owner_slug = create_test_owner_and_get_token(client, db_session, email="publicpage@example.com", slug="publicbiz")
    
    owner = crud.get_owner_by_slug(db_session, owner_slug)
    updated_services = [{"name": "Consultation", "duration": 60, "price": 100.0, "description": "Initial chat"}]
    updated_availability = [{"day_of_week": datetime.date.today().weekday(), "start_time": "09:00", "end_time": "17:00"}]
    owner.services_json = json.dumps(updated_services)
    owner.availability_json = json.dumps(updated_availability)
    db_session.add(owner)
    db_session.commit()
    db_session.refresh(owner)

    response = client.get(f"/{owner_slug}")
    assert response.status_code == 200
    assert "Book an Appointment with Test Business" in response.text
    assert "Consultation" in response.text
    assert "Initial chat" in response.text

@patch('src.notifications.send_email_notification')
@patch('src.notifications.send_whatsapp_notification')
def test_post_public_booking_success(mock_send_whatsapp, mock_send_email, client, db_session):
    token, owner_slug = create_test_owner_and_get_token(client, db_session, email="book@example.com", slug="bookbiz")
    
    owner = crud.get_owner_by_slug(db_session, owner_slug)
    today = datetime.date.today()
    updated_services = [{"name": "Service A", "duration": 60, "price": 50.0, "description": None}]
    updated_availability = [{"day_of_week": today.weekday(), "start_time": "09:00", "end_time": "17:00"}]
    owner.services_json = json.dumps(updated_services)
    owner.availability_json = json.dumps(updated_availability)
    db_session.add(owner)
    db_session.commit()
    db_session.refresh(owner)

    response = client.post(
        f"/{owner_slug}/book",
        data={
            "customer_name": "John Doe",
            "customer_email": "john.doe@example.com",
            "customer_phone": "+15551234567",
            "service_name": "Service A",
            "booking_date": today.strftime("%Y-%m-%d"),
            "booking_time": "10:00"
        }
    )
    assert response.status_code == 200
    assert "Booking Confirmed!" in response.text
    assert "You will receive an email confirmation shortly." in response.text

    mock_send_email.assert_called_with(
        "john.doe@example.com",
        "Your Booking for Service A is Confirmed!",
        pytest.approx(str, 0.1)
    )
    mock_send_email.assert_called_with(
        "book@example.com",
        "New Booking for Service A!",
        pytest.approx(str, 0.1)
    )
    mock_send_whatsapp.assert_called_with(
        "+15551234567",
        f"Your booking with Test Business for Service A on {today.strftime('%Y-%m-%d')} at 10:00 is confirmed."
    )
    mock_send_whatsapp.assert_called_with(
        "+1234567890",
        f"New booking for Service A on {today.strftime('%Y-%m-%d')} at 10:00 with John Doe."
    )

    bookings = crud.get_owner_bookings(db_session, owner.id)
    assert len(bookings) == 1
    assert bookings[0].customer_name == "John Doe"
    assert bookings[0].service_name == "Service A"

@patch('src.notifications.send_email_notification')
@patch('src.notifications.send_whatsapp_notification')
def test_post_public_booking_unavailable_time(mock_send_whatsapp, mock_send_email, client, db_session):
    token, owner_slug = create_test_owner_and_get_token(client, db_session, email="unavail@example.com", slug="unavailbiz")
    
    owner = crud.get_owner_by_slug(db_session, owner_slug)
    today = datetime.date.today()
    updated_services = [{"name": "Service B", "duration": 60, "price": 50.0, "description": None}]
    updated_availability = [{"day_of_week": (today.weekday() + 1) % 7, "start_time": "09:00", "end_time": "17:00"}]
    owner.services_json = json.dumps(updated_services)
    owner.availability_json = json.dumps(updated_availability)
    db_session.add(owner)
    db_session.commit()
    db_session.refresh(owner)

    response = client.post(
        f"/{owner_slug}/book",
        data={
            "customer_name": "Jane Doe",
            "customer_email": "jane.doe@example.com",
            "service_name": "Service B",
            "booking_date": today.strftime("%Y-%m-%d"),
            "booking_time": "10:00"
        }
    )
    assert response.status_code == 400
    assert "Selected time slot is not available." in response.text
    mock_send_email.assert_not_called()
    mock_send_whatsapp.assert_not_called()

@patch('src.notifications.send_email_notification')
@patch('src.notifications.send_whatsapp_notification')
def test_post_public_booking_already_booked(mock_send_whatsapp, mock_send_email, client, db_session):
    token, owner_slug = create_test_owner_and_get_token(client, db_session, email="alreadybooked@example.com", slug="bookedbiz")
    
    owner = crud.get_owner_by_slug(db_session, owner_slug)
    today = datetime.date.today()
    updated_services = [{"name": "Service C", "duration": 60, "price": 50.0, "description": None}]
    updated_availability = [{"day_of_week": today.weekday(), "start_time": "09:00", "end_time": "17:00"}]
    owner.services_json = json.dumps(updated_services)
    owner.availability_json = json.dumps(updated_availability)
    db_session.add(owner)
    db_session.commit()
    db_session.refresh(owner)

    client.post(
        f"/{owner_slug}/book",
        data={
            "customer_name": "First Guy",
            "customer_email": "first@example.com",
            "service_name": "Service C",
            "booking_date": today.strftime("%Y-%m-%d"),
            "booking_time": "11:00"
        }
    )
    response = client.post(
        f"/{owner_slug}/book",
        data={
            "customer_name": "Second Guy",
            "customer_email": "second@example.com",
            "service_name": "Service C",
            "booking_date": today.strftime("%Y-%m-%d"),
            "booking_time": "11:00"
        }
    )
    assert response.status_code == 409
    assert "This slot is already booked. Please choose another time." in response.text
    assert mock_send_email.call_count == 2
    assert mock_send_whatsapp.call_count == 2

def test_language_toggle_on_root(client):
    response = client.get("/?lang=ar")
    assert response.status_code == 200
    assert "مرحباً بك في بوك سلوت" in response.text

    response = client.get("/?lang=fr")
    assert response.status_code == 200
    assert "Bienvenue sur BookSlot" in response.text

    response = client.get("/?lang=en")
    assert response.status_code == 200
    assert "Welcome to BookSlot" in response.text

def test_language_toggle_on_dashboard(client, db_session):
    token, _ = create_test_owner_and_get_token(client, db_session, email="i18ndash@example.com", slug="i18ndashbiz")
    
    response = client.get(
        "/dashboard?lang=ar",
        cookies={"access_token": f"Bearer {token}"}
    )
    assert response.status_code == 200
    assert "أهلاً بك، Test Owner!" in response.text

    response = client.get(
        "/dashboard?lang=fr",
        cookies={"access_token": f"Bearer {token}"}
    )
    assert response.status_code == 200
    assert "Bienvenue, Test Owner!" in response.text

def test_language_toggle_on_booking_page(client, db_session):
    token, owner_slug = create_test_owner_and_get_token(client, db_session, email="i18nbook@example.com", slug="i18nbookbiz")
    
    owner = crud.get_owner_by_slug(db_session, owner_slug)
    owner.services_json = json.dumps([{"name": "i18n Service", "duration": 30, "price": 10.0, "description": None}])
    db_session.add(owner)
    db_session.commit()
    
    response = client.get(f"/{owner_slug}?lang=ar")
    assert response.status_code == 200
    assert "احجز موعدًا مع Test Business" in response.text
    assert "اختر الخدمة" in response.text

    response = client.get(f"/{owner_slug}?lang=fr")
    assert response.status_code == 200
    assert "Réservez un rendez-vous avec Test Business" in response.text
    assert "Sélectionner un service" in response.text

def test_api_owner_signup_invalid_email(client):
    response = client.post(
        "/api/owner/signup",
        json={
            "name": "Invalid Email",
            "email": "invalid-email",
            "password": "password",
            "business_name": "Invalid Email Biz",
            "slug": "invalid-email-biz"
        }
    )
    assert response.status_code == 422

def test_api_owner_profile_update_unauthenticated(client):
    response = client.put(
        "/api/owner/profile",
        json={
            "name": "New Name",
            "business_name": "New Biz",
            "phone": "+1234567890"
        },
        headers={"Authorization": "Bearer invalid_token"}
    )
    assert response.status_code == 401
    assert "Could not validate credentials" in response.json()["detail"]

def test_api_booking_invalid_date_format(client, db_session):
    token, owner_slug = create_test_owner_and_get_token(client, db_session, email="dateformat@example.com", slug="dateformatbiz")
    
    owner = crud.get_owner_by_slug(db_session, owner_slug)
    today = datetime.date.today()
    owner.services_json = json.dumps([{"name": "Service D", "duration": 60, "price": 50.0, "description": None}])
    owner.availability_json = json.dumps([{"day_of_week": today.weekday(), "start_time": "09:00", "end_time": "17:00"}])
    db_session.add(owner)
    db_session.commit()

    response = client.post(
        f"/api/booking/{owner_slug}",
        json={
            "customer_name": "Bad Date",
            "customer_email": "bad@example.com",
            "service_name": "Service D",
            "booking_date": "2023/10/26",
            "booking_time": "10:00"
        }
    )
    assert response.status_code == 422
