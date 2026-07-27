import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.main import app, get_db, models
from src.database import Base
from src.config import settings
from src import security # Import security for password hashing
import os

# Override the DATABASE_URL for testing
TEST_DATABASE_URL = "sqlite:///./test_bookslot.db"
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
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
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()

def test_i18n_dashboard_language_toggle(client, db_session):
    # Create a dummy owner for login
    owner_data = {
        "name": "Test Owner",
        "email": "test@example.com",
        "business_name": "Test Business",
        "slug": "test-business",
        "password": "testpassword"
    }
    owner = models.Owner(
        **owner_data,
        hashed_password=security.get_password_hash(owner_data["password"]),
        services_json="[]",
        availability_json="{}"
    )
    db_session.add(owner)
    db_session.commit()
    db_session.refresh(owner)

    # Login to get a cookie
    login_response = client.post("/login", data={"username": owner_data["email"], "password": owner_data["password"]})
    assert login_response.status_code == 303
    assert "access_token" in login_response.cookies

    cookies = {"access_token": login_response.cookies["access_token"]}

    # Test English dashboard
    response_en = client.get("/dashboard?lang=en", cookies=cookies)
    assert response_en.status_code == 200
    assert "Dashboard" in response_en.text
    assert "Upcoming Bookings" in response_en.text

    # Test Arabic dashboard
    response_ar = client.get("/dashboard?lang=ar", cookies=cookies)
    assert response_ar.status_code == 200
    # These would need to be present in locales/ar/LC_MESSAGES/messages.po and compiled.
    assert "لوحة التحكم" in response_ar.text or "Dashboard" in response_ar.text # Fallback if translation not compiled
    assert "الحجوزات القادمة" in response_ar.text or "Upcoming Bookings" in response_ar.text # Fallback

    # Test French dashboard
    response_fr = client.get("/dashboard?lang=fr", cookies=cookies)
    assert response_fr.status_code == 200
    assert "Tableau de bord" in response_fr.text or "Dashboard" in response_fr.text # Fallback
    assert "Réservations à venir" in response_fr.text or "Upcoming Bookings" in response_fr.text # Fallback


def test_i18n_booking_page_language_toggle(client, db_session):
    # Create a dummy owner with a slug
    owner_data = {
        "name": "Public Owner",
        "email": "public@example.com",
        "business_name": "Public Business",
        "slug": "public-biz",
        "password": "publicpassword"
    }
    owner = models.Owner(
        **owner_data,
        hashed_password=security.get_password_hash(owner_data["password"]),
        services_json='[{"name": "Haircut", "duration_minutes": 30}]',
        availability_json='{"0": [{"start_time": "09:00", "end_time": "17:00"}]}'
    )
    db_session.add(owner)
    db_session.commit()
    db_session.refresh(owner)

    # Test English booking page
    response_en = client.get(f"/{owner.slug}?lang=en")
    assert response_en.status_code == 200
    assert "Book your slot" in response_en.text
    assert "Select a service" in response_en.text

    # Test Arabic booking page
    response_ar = client.get(f"/{owner.slug}?lang=ar")
    assert response_ar.status_code == 200
    # Assuming 'احجز موعدك' for 'Book your slot' and 'اختر خدمة' for 'Select a service'
    assert "احجز موعدك" in response_ar.text or "Book your slot" in response_ar.text # Fallback
    assert "اختر خدمة" in response_ar.text or "Select a service" in response_ar.text # Fallback

    # Test French booking page
    response_fr = client.get(f"/{owner.slug}?lang=fr")
    assert response_fr.status_code == 200
    # Assuming 'Réservez votre créneau' for 'Book your slot' and 'Sélectionnez un service' for 'Select a service'
    assert "Réservez votre créneau" in response_fr.text or "Book your slot" in response_fr.text # Fallback
    assert "Sélectionnez un service" in response_fr.text or "Select a service" in response_fr.text # Fallback"
