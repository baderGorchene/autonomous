import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.main import app, get_db
from src.database import Base
from src import models, schemas, security
from unittest.mock import patch

# Setup test database
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

# Mock get_current_owner for dashboard tests
def mock_get_current_owner():
    hashed_password = security.get_password_hash("testpassword")
    return models.Owner(
        id=1,
        name="Test Owner",
        email="test@example.com",
        hashed_password=hashed_password,
        business_name="Test Business",
        slug="test-business",
        services_json=[],
        availability_json={},
        phone="1234567890"
    )

@patch("src.routes.auth.get_current_owner", new=mock_get_current_owner)
def test_dashboard_i18n_english(client, db_session):
    # Ensure owner exists for the dashboard
    owner = mock_get_current_owner()
    db_session.add(owner)
    db_session.commit()
    db_session.refresh(owner)

    response = client.get("/dashboard?lang=en")
    assert response.status_code == 200
    assert "Welcome" in response.text
    assert "My Bookings" in response.text
    assert "Upcoming Bookings" in response.text
    assert "Select Language" in response.text
    assert "اختر اللغة" not in response.text # Ensure Arabic is not present
    assert "Sélectionner la langue" not in response.text # Ensure French is not present

@patch("src.routes.auth.get_current_owner", new=mock_get_current_owner)
def test_dashboard_i18n_arabic(client, db_session):
    owner = mock_get_current_owner()
    db_session.add(owner)
    db_session.commit()
    db_session.refresh(owner)

    response = client.get("/dashboard?lang=ar")
    assert response.status_code == 200
    assert "Welcome" not in response.text # English should not be present
    assert "مرحباً" in response.text # Arabic translation for Welcome
    assert "حجوزاتي" in response.text # Arabic translation for My Bookings
    assert "الحجوزات القادمة" in response.text # Arabic translation for Upcoming Bookings
    assert "اختر اللغة" in response.text
    assert "Select Language" not in response.text # English should not be present
    assert "Sélectionner la langue" not in response.text # Ensure French is not present

@patch("src.routes.auth.get_current_owner", new=mock_get_current_owner)
def test_dashboard_i18n_french(client, db_session):
    owner = mock_get_current_owner()
    db_session.add(owner)
    db_session.commit()
    db_session.refresh(owner)

    response = client.get("/dashboard?lang=fr")
    assert response.status_code == 200
    assert "Welcome" not in response.text # English should not be present
    assert "Bienvenue" in response.text # French translation for Welcome
    assert "Mes Réservations" in response.text # French translation for My Bookings
    assert "Réservations à venir" in response.text # French translation for Upcoming Bookings
    assert "Sélectionner la langue" in response.text
    assert "Select Language" not in response.text # English should not be present
    assert "اختر اللغة" not in response.text # Ensure Arabic is not present


def test_booking_page_i18n_english(client, db_session):
    # Create a dummy owner for the booking page
    owner = models.Owner(
        name="BookSlot Owner",
        email="bookslot@example.com",
        hashed_password=security.get_password_hash("password"),
        business_name="BookSlot Salon",
        slug="bookslot-salon",
        services_json=[{"name": "Haircut", "duration": 30, "price": 50}],
        availability_json={"monday": [{"start": "09:00", "end": "17:00"}]},
        phone="1234567890"
    )
    db_session.add(owner)
    db_session.commit()
    db_session.refresh(owner)

    response = client.get(f"/book/{owner.slug}?lang=en")
    assert response.status_code == 200
    assert "Book an Appointment" in response.text
    assert "Select a service" in response.text
    assert "Select a date" in response.text
    assert "Book Now" in response.text
    assert "احجز موعدا" not in response.text
    assert "Réserver un rendez-vous" not in response.text


def test_booking_page_i18n_arabic(client, db_session):
    owner = models.Owner(
        name="BookSlot Owner",
        email="bookslot_ar@example.com",
        hashed_password=security.get_password_hash("password"),
        business_name="BookSlot Salon AR",
        slug="bookslot-salon-ar",
        services_json=[{"name": "Haircut", "duration": 30, "price": 50}],
        availability_json={"monday": [{"start": "09:00", "end": "17:00"}]},
        phone="1234567890"
    )
    db_session.add(owner)
    db_session.commit()
    db_session.refresh(owner)

    response = client.get(f"/book/{owner.slug}?lang=ar")
    assert response.status_code == 200
    assert "Book an Appointment" not in response.text
    assert "احجز موعدا" in response.text # Arabic translation for "Book an Appointment"
    assert "اختر خدمة" in response.text # Arabic translation for "Select a service"
    assert "اختر تاريخا" in response.text # Arabic translation for "Select a date"
    assert "احجز الآن" in response.text # Arabic translation for "Book Now"
    assert "Réserver un rendez-vous" not in response.text


def test_booking_page_i18n_french(client, db_session):
    owner = models.Owner(
        name="BookSlot Owner",
        email="bookslot_fr@example.com",
        hashed_password=security.get_password_hash("password"),
        business_name="BookSlot Salon FR",
        slug="bookslot-salon-fr",
        services_json=[{"name": "Haircut", "duration": 30, "price": 50}],
        availability_json={"monday": [{"start": "09:00", "end": "17:00"}]},
        phone="1234567890"
    )
    db_session.add(owner)
    db_session.commit()
    db_session.refresh(owner)

    response = client.get(f"/book/{owner.slug}?lang=fr")
    assert response.status_code == 200
    assert "Book an Appointment" not in response.text
    assert "Réserver un rendez-vous" in response.text # French translation for "Book an Appointment"
    assert "Sélectionner un service" in response.text # French translation for "Select a service"
    assert "Sélectionner une date" in response.text # French translation for "Select a date"
    assert "Réserver maintenant" in response.text # French translation for "Book Now"
    assert "احجز موعدا" not in response.text
