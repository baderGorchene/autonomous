import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.main import app, get_db, oauth2_scheme, get_current_owner
from src.database import Base
from src import models, schemas, security
from src.config import settings
from datetime import datetime, timedelta
import os
import json

SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
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
        try:
            yield db_session
        finally:
            db_session.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()

@pytest.fixture(name="owner_data")
def owner_data_fixture():
    return {
        "name": "Test Owner",
        "email": "test@example.com",
        "password": "testpassword",
        "business_name": "Test Business",
        "slug": "testbusiness",
        "phone": "+1234567890"
    }

@pytest.fixture(name="auth_owner")
def auth_owner_fixture(client, owner_data, db_session):
    owner_create = schemas.OwnerCreate(**owner_data)
    hashed_password = security.get_password_hash(owner_create.password)
    db_owner = models.Owner(
        name=owner_create.name,
        email=owner_create.email,
        hashed_password=hashed_password,
        business_name=owner_create.business_name,
        slug=owner_create.slug,
        phone=owner_data["phone"],
        services_json=[
            schemas.Service(name="Consultation", duration_minutes=30, price=50.0).dict(),
            schemas.Service(name="Follow-up", duration_minutes=60, price=100.0).dict(),
        ],
        availability_json={
            "Monday": [{"start_time": "09:00", "end_time": "17:00"}],
            "Tuesday": [{"start_time": "09:00", "end_time": "17:00"}],
            "Wednesday": [{"start_time": "09:00", "end_time": "17:00"}],
            "Thursday": [{"start_time": "09:00", "end_time": "17:00"}],
            "Friday": [{"start_time": "09:00", "end_time": "17:00"}],
        }
    )
    db_session.add(db_owner)
    db_session.commit()
    db_session.refresh(db_owner)

    response = client.post("/token", data={"username": owner_data["email"], "password": owner_data["password"]})
    assert response.status_code == 200
    token = response.json()["access_token"]
    return db_owner, token

@pytest.fixture(name="mock_notifications")
def mock_notifications_fixture(mocker):
    mocker.patch("src.notifications.send_email_notification", return_value=True)
    mocker.patch("src.notifications.send_whatsapp_notification", return_value=True)
    return mocker

def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_signup_page(client):
    response = client.get("/signup")
    assert response.status_code == 200
    assert "Sign Up for BookSlot" in response.text

def test_signup_owner(client, owner_data):
    response = client.post("/signup", data=owner_data)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"

    db = TestingSessionLocal()
    owner = db.query(models.Owner).filter(models.Owner.email == owner_data["email"]).first()
    assert owner is not None
    assert owner.name == owner_data["name"]
    db.close()

def test_signup_duplicate_email(client, owner_data):
    client.post("/signup", data=owner_data)
    response = client.post("/signup", data=owner_data)
    assert response.status_code == 200
    assert "Email already registered" in response.text

def test_signup_duplicate_slug(client, owner_data):
    client.post("/signup", data=owner_data)
    owner_data_2 = owner_data.copy()
    owner_data_2["email"] = "test2@example.com"
    response = client.post("/signup", data=owner_data_2)
    assert response.status_code == 200
    assert "Slug already taken" in response.text

def test_login_page(client):
    response = client.get("/login")
    assert response.status_code == 200
    assert "Login to BookSlot" in response.text

def test_login_successful(client, owner_data):
    client.post("/signup", data=owner_data)
    response = client.post("/login", data={"email": owner_data["email"], "password": owner_data["password"]})
    assert response.status_code == 303
    assert response.headers["location"] == "/dashboard"
    assert "access_token" in response.cookies

def test_login_invalid_credentials(client, owner_data):
    client.post("/signup", data=owner_data)
    response = client.post("/login", data={"email": owner_data["email"], "password": "wrongpassword"})
    assert response.status_code == 303
    assert "/login?error=Invalid credentials" in response.headers["location"]

def test_dashboard_access_unauthenticated(client):
    response = client.get("/dashboard")
    assert response.status_code == 401

def test_dashboard_access_authenticated(client, auth_owner):
    owner, token = auth_owner
    response = client.get("/dashboard", cookies={"access_token": token})
    assert response.status_code == 200
    assert owner.business_name in response.text
    assert "Upcoming Bookings" in response.text

def test_update_profile_success(client, auth_owner):
    owner, token = auth_owner
    new_name = "Updated Name"
    new_business_name = "New Business Inc."
    new_phone = "+9876543210"
    
    response = client.post("/dashboard/profile", 
                           data={"name": new_name, "business_name": new_business_name, "phone": new_phone},
                           cookies={"access_token": token})
    assert response.status_code == 200
    assert "Profile updated successfully!" in response.text
    assert new_name in response.text
    assert new_business_name in response.text
    assert new_phone in response.text

    db = TestingSessionLocal()
    updated_owner = db.query(models.Owner).filter(models.Owner.id == owner.id).first()
    assert updated_owner.name == new_name
    assert updated_owner.business_name == new_business_name
    assert updated_owner.phone == new_phone
    db.close()

def test_update_profile_error_unauthenticated(client):
    response = client.post("/dashboard/profile", data={"name": "x", "business_name": "y", "phone": "z"})
    assert response.status_code == 401

def test_public_booking_page_renders(client, auth_owner):
    owner, _ = auth_owner
    response = client.get(f"/{owner.slug}")
    assert response.status_code == 200
    assert owner.business_name in response.text
    assert "Book Your Appointment" in response.text
    assert owner.services_json[0]['name'] in response.text

def test_public_booking_page_not_found(client):
    response = client.get("/nonexistent-slug")
    assert response.status_code == 404
    assert "Owner not found" in response.json()["detail"]

def test_booking_submission_success(client, auth_owner, mock_notifications):
    owner, _ = auth_owner
    booking_time = (datetime.utcnow() + timedelta(days=1, hours=2)).strftime("%Y-%m-%d %H:%M")
    booking_date = booking_time.split(" ")[0]
    booking_time_str = booking_time.split(" ")[1]

    response = client.post(
        f"/{owner.slug}/book",
        data={
            "customer_name": "Jane Doe",
            "customer_email": "jane@example.com",
            "customer_phone": "+1987654321",
            "service_name": owner.services_json[0]['name'],
            "booking_date": booking_date,
            "booking_time": booking_time_str,
        },
    )
    assert response.status_code == 200
    assert "Booking Confirmed!" in response.text
    assert mock_notifications.patch.call_count == 4

    db = TestingSessionLocal()
    booking = db.query(models.Booking).filter(models.Booking.customer_email == "jane@example.com").first()
    assert booking is not None
    assert booking.owner_id == owner.id
    assert booking.service_name == owner.services_json[0]['name']
    db.close()

def test_booking_submission_past_date_error(client, auth_owner):
    owner, _ = auth_owner
    past_booking_time = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M")
    booking_date = past_booking_time.split(" ")[0]
    booking_time_str = past_booking_time.split(" ")[1]

    response = client.post(
        f"/{owner.slug}/book",
        data={
            "customer_name": "Jane Doe",
            "customer_email": "jane@example.com",
            "customer_phone": "+1987654321",
            "service_name": owner.services_json[0]['name'],
            "booking_date": booking_date,
            "booking_time": booking_time_str,
        },
    )
    assert response.status_code == 200
    assert "Booking must be in the future." in response.text

def test_booking_submission_invalid_service_error(client, auth_owner):
    owner, _ = auth_owner
    booking_time = (datetime.utcnow() + timedelta(days=1)).strftime("%Y-%m-%d %H:%M")
    booking_date = booking_time.split(" ")[0]
    booking_time_str = booking_time.split(" ")[1]

    response = client.post(
        f"/{owner.slug}/book",
        data={
            "customer_name": "Jane Doe",
            "customer_email": "jane@example.com",
            "customer_phone": "+1987654321",
            "service_name": "NonExistentService",
            "booking_date": booking_date,
            "booking_time": booking_time_str,
        },
    )
    assert response.status_code == 200
    assert "Selected service not found." in response.text

def test_booking_submission_already_booked_slot_error(client, auth_owner, mock_notifications):
    owner, _ = auth_owner
    booking_dt_future = datetime.utcnow() + timedelta(days=2, hours=1)
    booking_date = booking_dt_future.strftime("%Y-%m-%d")
    booking_time_str = booking_dt_future.strftime("%H:%M")

    client.post(
        f"/{owner.slug}/book",
        data={
            "customer_name": "Jane Doe",
            "customer_email": "jane@example.com",
            "customer_phone": "+1987654321",
            "service_name": owner.services_json[0]['name'],
            "booking_date": booking_date,
            "booking_time": booking_time_str,
        },
    )
    response = client.post(
        f"/{owner.slug}/book",
        data={
            "customer_name": "John Smith",
            "customer_email": "john@example.com",
            "customer_phone": "+1123456789",
            "service_name": owner.services_json[0]['name'],
            "booking_date": booking_date,
            "booking_time": booking_time_str,
        },
    )
    assert response.status_code == 200
    assert "This time slot is already booked." in response.text

from bs4 import BeautifulSoup

def test_language_toggle_on_booking_page(client, auth_owner):
    owner, _ = auth_owner
    
    response = client.get(f"/{owner.slug}")
    assert response.status_code == 200
    assert "Book Your Appointment" in response.text
    assert "Your Name" in response.text
    assert "Select Date" in response.text

    response = client.post("/set-language", data={"lang": "ar"}, follow_redirects=False)
    assert response.status_code == 303
    assert response.cookies["lang"] == "ar"

    response = client.get(f"/{owner.slug}", cookies={"lang": "ar"})
    assert response.status_code == 200
    soup = BeautifulSoup(response.text, "html.parser")
    assert "احجز موعدك" in soup.text
    assert "اسمك" in soup.text
    assert "اختر التاريخ" in soup.text

    response = client.post("/set-language", data={"lang": "fr"}, follow_redirects=False)
    assert response.status_code == 303
    assert response.cookies["lang"] == "fr"

    response = client.get(f"/{owner.slug}", cookies={"lang": "fr"})
    assert response.status_code == 200
    soup = BeautifulSoup(response.text, "html.parser")
    assert "Réservez votre rendez-vous" in soup.text
    assert "Votre nom" in soup.text
    assert "Sélectionner la date" in soup.text

def test_language_toggle_on_dashboard(client, auth_owner):
    owner, token = auth_owner

    response = client.get("/dashboard", cookies={"access_token": token})
    assert response.status_code == 200
    assert "Welcome" in response.text
    assert "Upcoming Bookings" in response.text

    response = client.post("/set-language", data={"lang": "ar"}, follow_redirects=False)
    assert response.status_code == 303
    assert response.cookies["lang"] == "ar"

    response = client.get("/dashboard", cookies={"access_token": token, "lang": "ar"})
    assert response.status_code == 200
    soup = BeautifulSoup(response.text, "html.parser")
    assert "أهلاً بك" in soup.text
    assert "الحجوزات القادمة" in soup.text

    response = client.post("/set-language", data={"lang": "fr"}, follow_redirects=False)
    assert response.status_code == 303
    assert response.cookies["lang"] == "fr"

    response = client.get("/dashboard", cookies={"access_token": token, "lang": "fr"})
    assert response.status_code == 200
    soup = BeautifulSoup(response.text, "html.parser")
    assert "Bienvenue" in soup.text
    assert "Réservations à venir" in soup.text
