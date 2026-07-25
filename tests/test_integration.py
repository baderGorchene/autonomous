from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from src import crud, models, schemas, security
from datetime import datetime, timedelta
import pytz
import pytest

from src.config import settings
settings.SENDGRID_API_KEY = "test_sendgrid_key"
settings.TWILIO_ACCOUNT_SID = "test_twilio_sid"
settings.TWILIO_AUTH_TOKEN = "test_twilio_token"
settings.TWILIO_WHATSAPP_NUMBER = "+15005550006"
settings.GEMINI_API_KEY = "test_gemini_key"
settings.SECRET_KEY = "super-secret-test-key"

def test_owner_signup_and_login(client: TestClient, db_session: Session, test_owner_data: dict):
    response = client.post(
        "/signup",
        data=test_owner_data,
        follow_redirects=False
    )
    assert response.status_code == 302
    assert response.headers["location"] == "/dashboard"

    owner_in_db = crud.get_owner_by_email(db_session, email=test_owner_data["email"])
    assert owner_in_db is not None
    assert owner_in_db.name == test_owner_data["name"]
    assert owner_in_db.business_name == test_owner_data["business_name"]
    assert owner_in_db.slug == test_owner_data["slug"]
    assert security.verify_password(test_owner_data["password"], owner_in_db.hashed_password)

    response = client.post(
        "/token",
        data={"username": test_owner_data["email"], "password": test_owner_data["password"]}
    )
    assert response.status_code == 200
    token_data = response.json()
    assert "access_token" in token_data
    assert token_data["token_type"] == "bearer"
    assert "access_token" in client.cookies

    response = client.post(
        "/token",
        data={"username": test_owner_data["email"], "password": "wrongpassword"}
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect email or password"

    response = client.post(
        "/token",
        data={"username": "nonexistent@example.com", "password": "anypassword"}
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect email or password"

def test_signup_duplicate_email_or_slug(client: TestClient, db_session: Session, create_test_owner: models.Owner):
    duplicate_email_data = {
        "name": "Another Owner",
        "email": create_test_owner.email,
        "password": "password123",
        "business_name": "Another Business",
        "slug": "another-business",
    }
    response = client.post("/signup", data=duplicate_email_data)
    assert response.status_code == 200
    assert "Email already registered" in response.text

    duplicate_slug_data = {
        "name": "Yet Another Owner",
        "email": "yetanother@example.com",
        "password": "password123",
        "business_name": "Yet Another Business",
        "slug": create_test_owner.slug,
    }
    response = client.post("/signup", data=duplicate_slug_data)
    assert response.status_code == 200
    assert "Business URL slug already taken" in response.text

def test_owner_dashboard_access(client: TestClient, create_test_owner: models.Owner):
    response = client.get("/dashboard")
    assert response.status_code == 401

    response = client.post(
        "/token",
        data={"username": create_test_owner.email, "password": "testpassword"}
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    client.cookies["access_token"] = token

    response = client.get("/dashboard")
    assert response.status_code == 200
    assert "Dashboard" in response.text
    assert create_test_owner.business_name in response.text
    assert create_test_owner.name in response.text

def test_owner_profile_update(authenticated_client: TestClient, db_session: Session, create_test_owner: models.Owner):
    new_name = "Updated Name"
    new_business_name = "Updated Business"
    new_phone = "+1987654321"

    response = authenticated_client.post(
        "/dashboard/profile",
        data=
            {
            "name": new_name,
            "business_name": new_business_name,
            "phone": new_phone
        }
    )
    assert response.status_code == 200
    assert "Profile updated successfully!" in response.text
    assert new_name in response.text
    assert new_business_name in response.text
    assert new_phone in response.text

    updated_owner = crud.get_owner(db_session, create_test_owner.id)
    assert updated_owner.name == new_name
    assert updated_owner.business_name == new_business_name
    assert updated_owner.phone == new_phone

def test_public_booking_page_loads(client: TestClient, create_test_owner: models.Owner):
    response = client.get(f"/bookslot.app/{create_test_owner.slug}")
    assert response.status_code == 200
    assert create_test_owner.business_name in response.text
    assert "Book an Appointment" in response.text
    assert "Haircut" in response.text
    assert "09:00 AM" in response.text

def test_public_booking_page_not_found(client: TestClient):
    response = client.get("/bookslot.app/non-existent-slug")
    assert response.status_code == 404
    assert "Owner not found" in response.text

def test_booking_submission_success(client: TestClient, db_session: Session, create_test_owner: models.Owner):
    booking_date = (datetime.now(pytz.utc) + timedelta(days=7)).strftime("%Y-%m-%d")
    booking_time = "10:00"

    booking_data = {
        "customer_name": "Jane Doe",
        "customer_email": "jane@example.com",
        "customer_phone": "+19998887777",
        "service_name": "Haircut",
        "booking_date": booking_date,
        "booking_time": booking_time,
    }

    response = client.post(
        f"/bookslot.app/{create_test_owner.slug}/book",
        data=booking_data,
        follow_redirects=False
    )
    assert response.status_code == 302
    assert "confirmation" in response.headers["location"]

    bookings_in_db = db_session.query(models.Booking).filter(models.Booking.owner_id == create_test_owner.id).all()
    assert len(bookings_in_db) == 1
    new_booking = bookings_in_db[0]
    assert new_booking.customer_name == booking_data["customer_name"]
    assert new_booking.service_name == booking_data["service_name"]
    assert new_booking.booking_time.strftime("%Y-%m-%d %H:%M") == datetime.strptime(f"{booking_date} {booking_time}", "%Y-%m-%d %H:%M").strftime("%Y-%m-%d %H:%M")

    confirmation_url = response.headers["location"]
    response = client.get(confirmation_url)
    assert response.status_code == 200
    assert "Booking Confirmed!" in response.text
    assert str(new_booking.id) in response.text

def test_booking_submission_error_past_time(client: TestClient, db_session: Session, create_test_owner: models.Owner):
    booking_date = (datetime.now(pytz.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    booking_time = "10:00"

    booking_data = {
        "customer_name": "Error User",
        "customer_email": "error@example.com",
        "customer_phone": "+1234567890",
        "service_name": "Haircut",
        "booking_date": booking_date,
        "booking_time": booking_time,
    }

    response = client.post(
        f"/bookslot.app/{create_test_owner.slug}/book",
        data=booking_data
    )
    assert response.status_code == 200
    assert "Booking must be in the future." in response.text
    
    bookings_in_db = db_session.query(models.Booking).filter(models.Booking.owner_id == create_test_owner.id).all()
    assert len(bookings_in_db) == 0

def test_i18n_language_toggle_booking_page(client: TestClient, create_test_owner: models.Owner):
    response = client.get(f"/bookslot.app/{create_test_owner.slug}")
    assert response.status_code == 200
    assert "Book an Appointment" in response.text
    assert "Your Name:" in response.text

    response = client.get(f"/toggle-lang?lang=ar", headers={"referer": f"/bookslot.app/{create_test_owner.slug}"})
    assert response.status_code == 302
    assert client.cookies["lang"] == "ar"
    response = client.get(f"/bookslot.app/{create_test_owner.slug}")
    assert response.status_code == 200
    assert "احجز موعداً" in response.text
    assert "اسمك:" in response.text

    response = client.get(f"/toggle-lang?lang=fr", headers={"referer": f"/bookslot.app/{create_test_owner.slug}"})
    assert response.status_code == 302
    assert client.cookies["lang"] == "fr"
    response = client.get(f"/bookslot.app/{create_test_owner.slug}")
    assert response.status_code == 200
    assert "Prendre rendez-vous" in response.text
    assert "Votre nom :" in response.text

def test_i18n_language_toggle_dashboard_page(authenticated_client: TestClient, create_test_owner: models.Owner):
    response = authenticated_client.get("/dashboard")
    assert response.status_code == 200
    assert "Dashboard" in response.text
    assert "Your Profile" in response.text

    response = authenticated_client.get(f"/toggle-lang?lang=ar", headers={"referer": "/dashboard"})
    assert response.status_code == 302
    assert authenticated_client.cookies["lang"] == "ar"
    response = authenticated_client.get("/dashboard")
    assert response.status_code == 200
    assert "لوحة التحكم" in response.text
    assert "ملفك الشخصي" in response.text

    response = authenticated_client.get(f"/toggle-lang?lang=fr", headers={"referer": "/dashboard"})
    assert response.status_code == 302
    assert authenticated_client.cookies["lang"] == "fr"
    response = authenticated_client.get("/dashboard")
    assert response.status_code == 200
    assert "Tableau de bord" in response.text
    assert "Votre profil" in response.text
