import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.main import app, get_db
from src.database import Base
from src import models, crud, security, schemas
from datetime import datetime, timedelta

SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(name="db")
def session_fixture():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)

@pytest.fixture(name="client")
def client_fixture(db: TestingSessionLocal):
    def override_get_db():
        try:
            yield db
        finally:
            db.close()
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()

@pytest.fixture
def test_owner(db: TestingSessionLocal):
    owner_create = schemas.OwnerCreate(
        name="Test Owner",
        email="test@example.com",
        password="testpassword",
        business_name="Test Business",
        slug="test-business-slug"
    )
    owner = crud.create_owner(db, owner_create)
    return owner

@pytest.fixture
def authenticated_client(client: TestClient, test_owner: models.Owner):
    response = client.post(
        "/auth/token",
        data={"username": test_owner.email, "password": "testpassword"}
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    return client

def test_dashboard_language_arabic(authenticated_client: TestClient, test_owner: models.Owner, db: TestingSessionLocal):
    booking_data = schemas.BookingCreate(
        customer_name="John Doe",
        customer_email="john@example.com",
        customer_phone="1234567890",
        service="Haircut",
        datetime=datetime.now() + timedelta(days=1)
    )
    crud.create_booking(db, booking_data, test_owner.id)

    response = authenticated_client.get("/dashboard?lang=ar")
    assert response.status_code == 200
    assert "الحجوزات القادمة" in response.text or "مرحباً بك في لوحة التحكم الخاصة بك" in response.text

def test_dashboard_language_french(authenticated_client: TestClient, test_owner: models.Owner, db: TestingSessionLocal):
    booking_data = schemas.BookingCreate(
        customer_name="Jane Doe",
        customer_email="jane@example.com",
        customer_phone="0987654321",
        service="Massage",
        datetime=datetime.now() + timedelta(days=2)
    )
    crud.create_booking(db, booking_data, test_owner.id)

    response = authenticated_client.get("/dashboard?lang=fr")
    assert response.status_code == 200
    assert "Réservations à venir" in response.text or "Bienvenue sur votre tableau de bord" in response.text

def test_booking_page_language_arabic(client: TestClient, test_owner: models.Owner):
    response = client.get(f"/book/{test_owner.slug}?lang=ar")
    assert response.status_code == 200
    assert "احجز موعداً" in response.text or "الرجاء إدخال بياناتك" in response.text

def test_booking_page_language_french(client: TestClient, test_owner: models.Owner):
    response = client.get(f"/book/{test_owner.slug}?lang=fr")
    assert response.status_code == 200
    assert "Prendre un rendez-vous" in response.text or "Veuillez entrer vos coordonnées" in response.text

def test_booking_page_default_language_english(client: TestClient, test_owner: models.Owner):
    response = client.get(f"/book/{test_owner.slug}")
    assert response.status_code == 200
    assert "Book an appointment" in response.text or "Please enter your details" in response.text

def test_dashboard_default_language_english(authenticated_client: TestClient, test_owner: models.Owner):
    response = authenticated_client.get("/dashboard")
    assert response.status_code == 200
    assert "Upcoming Bookings" in response.text or "Welcome to your dashboard" in response.text
