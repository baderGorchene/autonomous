import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy_utils import database_exists, create_database, drop_database

from src.main import app, get_db
from src.database import Base
from src.config import settings
from src import models, security, crud, schemas
import json
import os
from datetime import date, datetime

# Use a separate test database
TEST_DATABASE_URL = "sqlite:///./test.db"

@pytest.fixture(scope="session")
def test_engine():
    # Only create/drop if it's a file-based sqlite db, or handle postgres/mysql differently
    if "sqlite" in TEST_DATABASE_URL and os.path.exists("./test.db"):
        os.remove("./test.db")
    
    test_engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=test_engine)
    yield test_engine
    Base.metadata.drop_all(bind=test_engine)
    if "sqlite" in TEST_DATABASE_URL and os.path.exists("./test.db"):
        os.remove("./test.db")

@pytest.fixture(scope="function")
def db_session(test_engine):
    connection = test_engine.connect()
    transaction = connection.begin()
    SessionTesting = sessionmaker(autocommit=False, autoflush=False, bind=connection)
    session = SessionTesting()
    yield session
    session.close()
    transaction.rollback()
    connection.close()

@pytest.fixture(scope="function")
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            db_session.close()
    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()

@pytest.fixture
def test_owner_data():
    return {
        "name": "Test Owner",
        "email": "test@example.com",
        "password": "testpassword",
        "business_name": "Test Business",
        "slug": "test-business",
        "phone": "+15551234567"
    }

@pytest.fixture
def auth_owner(client, db_session, test_owner_data):
    # Create owner
    owner_create = schemas.OwnerCreate(**test_owner_data)
    owner = crud.create_owner(db_session, owner_create)
    
    # Login and get token
    response = client.post(
        "/login",
        data={"email": test_owner_data["email"], "password": test_owner_data["password"]}
    )
    assert response.status_code == 302
    # Extract token from cookie
    access_token = response.cookies.get("access_token")
    assert access_token is not None
    return owner, access_token

# --- Test Cases ---

def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_signup_and_login(client, db_session, test_owner_data):
    # Test signup
    response = client.post(
        "/signup",
        data=test_owner_data
    )
    assert response.status_code == 200
    assert "Account created successfully!" in response.text
    
    owner_in_db = crud.get_owner_by_email(db_session, test_owner_data["email"])
    assert owner_in_db is not None
    assert owner_in_db.email == test_owner_data["email"]

    # Test login
    response = client.post(
        "/login",
        data={"email": test_owner_data["email"], "password": test_owner_data["password"]}
    )
    assert response.status_code == 302
    assert response.headers["location"] == "/dashboard"
    assert "access_token" in response.cookies

def test_duplicate_email_signup(client, db_session, test_owner_data):
    # First signup
    client.post("/signup", data=test_owner_data)

    # Second signup with same email
    response = client.post("/signup", data=test_owner_data)
    assert response.status_code == 400
    assert "Email already registered" in response.text

def test_duplicate_slug_signup(client, db_session, test_owner_data):
    # First signup
    client.post("/signup", data=test_owner_data)
    
    # Second signup with different email but same slug
    new_owner_data = test_owner_data.copy()
    new_owner_data["email"] = "newtest@example.com"
    response = client.post("/signup", data=new_owner_data)
    assert response.status_code == 400
    assert "Business URL already taken" in response.text

def test_owner_dashboard_access(client, auth_owner):
    owner, access_token = auth_owner
    response = client.get("/dashboard", cookies={"access_token": access_token})
    assert response.status_code == 200
    assert f"Welcome, {owner.name}!" in response.text

def test_owner_profile_update(client, db_session, auth_owner):
    owner, access_token = auth_owner
    updated_name = "Updated Name"
    updated_business_name = "Updated Business"
    updated_phone = "+19876543210"
    services_data = json.dumps([{"name": "Haircut", "duration": 60, "price": 50.0}])
    availability_data = json.dumps([{"day_of_week": 0, "start_time": "09:00", "end_time": "17:00"}])

    response = client.post(
        "/profile",
        cookies={"access_token": access_token},
        data={
            "name": updated_name,
            "business_name": updated_business_name,
            "phone": updated_phone,
            "services_data": services_data,
            "availability_data": availability_data
        }
    )
    assert response.status_code == 200
    assert "Profile updated successfully!" in response.text

    updated_owner = crud.get_owner(db_session, owner.id)
    assert updated_owner.name == updated_name
    assert updated_owner.business_name == updated_business_name
    assert updated_owner.phone == updated_phone
    assert json.loads(updated_owner.services_json)[0]['name'] == "Haircut"
    assert json.loads(updated_owner.availability_json)[0]['day_of_week'] == 0

def test_public_booking_page(client, db_session, auth_owner):
    owner, _ = auth_owner
    
    # Update owner with services and availability for the booking page to display them
    owner.services_json = json.dumps([{"name": "Service A", "duration": 30, "price": 25.0}])
    owner.availability_json = json.dumps([{"day_of_week": date.today().weekday(), "start_time": "09:00", "end_time": "17:00"}])
    db_session.add(owner)
    db_session.commit()
    db_session.refresh(owner)

    response = client.get(f"/book/{owner.slug}")
    assert response.status_code == 200
    assert owner.business_name in response.text
    assert "Service A" in response.text
    assert "Choose a date" in response.text

def test_submit_booking(client, db_session, auth_owner, monkeypatch):
    owner, _ = auth_owner

    # Mock notification functions
    mock_email_sent = []
    mock_whatsapp_sent = []

    def mock_send_email_notification(to_email, subject, html_content):
        mock_email_sent.append({"to": to_email, "subject": subject, "content": html_content})
        return True

    def mock_send_whatsapp_notification(to_phone_number, message_body):
        mock_whatsapp_sent.append({"to": to_phone_number, "body": message_body})
        return True

    monkeypatch.setattr("src.notifications.send_email_notification", mock_send_email_notification)
    monkeypatch.setattr("src.notifications.send_whatsapp_notification", mock_send_whatsapp_notification)

    # Update owner with services and availability
    today_weekday = date.today().weekday()
    current_hour = datetime.now().hour
    next_hour = (current_hour + 1) % 24 # Ensure time is in the future if running today
    booking_time = f"{next_hour:02d}:00"

    owner.services_json = json.dumps([{"name": "Test Service", "duration": 60, "price": 100.0}])
    owner.availability_json = json.dumps([{"day_of_week": today_weekday, "start_time": f"{current_hour:02d}:00", "end_time": "23:00"}])
    db_session.add(owner)
    db_session.commit()
    db_session.refresh(owner)

    booking_data = {
        "customer_name": "Jane Doe",
        "customer_email": "jane.doe@example.com",
        "customer_phone": "+1234567890",
        "service_name": "Test Service",
        "booking_date": date.today().strftime("%Y-%m-%d"),
        "booking_time": booking_time
    }

    response = client.post(f"/book/{owner.slug}/submit", data=booking_data)
    assert response.status_code == 302
    assert response.headers["location"] == "/booking-confirmation"

    # Check if booking was created in DB
    bookings = crud.get_owner_bookings(db_session, owner.id)
    assert len(bookings) == 1
    assert bookings[0].customer_email == booking_data["customer_email"]

    # Check if notifications were called
    assert len(mock_email_sent) == 2 # One for customer, one for owner
    assert len(mock_whatsapp_sent) == 1 # One for owner
    assert "jane.doe@example.com" in [e["to"] for e in mock_email_sent]
    assert owner.email in [e["to"] for e in mock_email_sent]
    assert owner.phone in [w["to"] for w in mock_whatsapp_sent]

def test_submit_booking_invalid_service(client, db_session, auth_owner):
    owner, _ = auth_owner
    owner.services_json = json.dumps([{"name": "Valid Service", "duration": 60, "price": 100.0}])
    owner.availability_json = json.dumps([{"day_of_week": date.today().weekday(), "start_time": "09:00", "end_time": "17:00"}])
    db_session.add(owner)
    db_session.commit()
    db_session.refresh(owner)

    booking_data = {
        "customer_name": "Jane Doe",
        "customer_email": "jane.doe@example.com",
        "customer_phone": "+1234567890",
        "service_name": "Invalid Service", # This service does not exist
        "booking_date": date.today().strftime("%Y-%m-%d"),
        "booking_time": "10:00"
    }
    response = client.post(f"/book/{owner.slug}/submit", data=booking_data)
    assert response.status_code == 400
    assert "Selected service is not available." in response.text

def test_submit_booking_invalid_time_slot(client, db_session, auth_owner):
    owner, _ = auth_owner
    owner.services_json = json.dumps([{"name": "Test Service", "duration": 60, "price": 100.0}])
    # Set availability to a different day or a very narrow window
    owner.availability_json = json.dumps([{"day_of_week": (date.today().weekday() + 1) % 7, "start_time": "09:00", "end_time": "17:00"}])
    db_session.add(owner)
    db_session.commit()
    db_session.refresh(owner)

    booking_data = {
        "customer_name": "Jane Doe",
        "customer_email": "jane.doe@example.com",
        "customer_phone": "+1234567890",
        "service_name": "Test Service",
        "booking_date": date.today().strftime("%Y-%m-%d"), # Try to book for today
        "booking_time": "10:00"
    }
    response = client.post(f"/book/{owner.slug}/submit", data=booking_data)
    assert response.status_code == 400
    assert "Selected time slot is not available or outside business hours." in response.text

def test_booking_confirmation_page(client):
    response = client.get("/booking-confirmation")
    assert response.status_code == 200
    assert "Booking Confirmed!" in response.text

