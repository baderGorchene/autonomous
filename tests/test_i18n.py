import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.database import Base
from src.main import app, get_db
from src.models import Owner, Booking
from src.routes import auth
import os

# Setup in-memory SQLite for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(name="session")
def session_fixture():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)

@pytest.fixture(name="client")
def client_fixture(session):
    def override_get_db():
        yield session
    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()

# Mock current owner for authenticated routes
@pytest.fixture
def mock_owner(session):
    owner = Owner(
        id=1,
        name="Test Owner",
        email="owner@example.com",
        hashed_password="hashed_password",
        business_name="Test Business",
        slug="test-business",
        services_json=[{"name": "Service 1", "duration": 30}],
        availability_json={"monday": [{"start": "09:00", "end": "17:00"}]},
        phone="1234567890"
    )
    session.add(owner)
    session.commit()
    session.refresh(owner)
    return owner

@pytest.fixture
def override_auth_dependency(mock_owner):
    def _override_get_current_owner():
        return mock_owner
    app.dependency_overrides[auth.get_current_owner] = _override_get_current_owner
    yield
    app.dependency_overrides.clear()

def test_dashboard_i18n_en(client, override_auth_dependency, mock_owner):
    response = client.get("/dashboard?lang=en")
    assert response.status_code == 200
    assert "Dashboard" in response.text
    assert "Upcoming Bookings" in response.text
    assert 'href="?lang=ar"' in response.text
    assert 'href="?lang=fr"' in response.text

def test_dashboard_i18n_ar(client, override_auth_dependency, mock_owner):
    response = client.get("/dashboard?lang=ar")
    assert response.status_code == 200
    assert "لوحة التحكم" in response.text
    assert "الحجوزات القادمة" in response.text
    assert 'href="?lang=en"' in response.text
    assert 'href="?lang=fr"' in response.text

def test_dashboard_i18n_fr(client, override_auth_dependency, mock_owner):
    response = client.get("/dashboard?lang=fr")
    assert response.status_code == 200
    assert "Tableau de bord" in response.text
    assert "Prochaines réservations" in response.text
    assert 'href="?lang=en"' in response.text
    assert 'href="?lang=ar"' in response.text

def test_booking_page_i18n_en(client, mock_owner):
    response = client.get(f"/book/{mock_owner.slug}?lang=en")
    assert response.status_code == 200
    assert "Book a Slot" in response.text
    assert "Select a Service" in response.text
    assert 'href="?lang=ar"' in response.text
    assert 'href="?lang=fr"' in response.text

def test_booking_page_i18n_ar(client, mock_owner):
    response = client.get(f"/book/{mock_owner.slug}?lang=ar")
    assert response.status_code == 200
    assert "احجز موعدا" in response.text
    assert "اختر خدمة" in response.text
    assert 'href="?lang=en"' in response.text
    assert 'href="?lang=fr"' in response.text

def test_booking_page_i18n_fr(client, mock_owner):
    response = client.get(f"/book/{mock_owner.slug}?lang=fr")
    assert response.status_code == 200
    assert "Réserver un créneau" in response.text
    assert "Sélectionnez un service" in response.text
    assert 'href="?lang=en"' in response.text
    assert 'href="?lang=ar"' in response.text