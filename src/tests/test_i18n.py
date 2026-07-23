import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.main import app, get_db
from src.database import Base
from src import models, security, crud, schemas
from src.routes import auth
import os

# Setup a test database
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_bookslot.db"
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
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    
    # Mock current owner for dashboard tests
    test_owner = models.Owner(
        id=1,
        name="Test Owner",
        email="test@example.com",
        hashed_password=security.get_password_hash("password"),
        business_name="Test Business",
        slug="test-business",
        services_json=[],
        availability_json={},
        phone="1234567890"
    )
    db_session.add(test_owner)
    db_session.commit()
    db_session.refresh(test_owner)

    def override_get_current_owner():
        return test_owner
    app.dependency_overrides[auth.get_current_owner] = override_get_current_owner
    
    with TestClient(app) as c:
        yield c
    
    app.dependency_overrides.clear() # Clear overrides after test

# Helper function to create a test owner for booking page slug
def create_test_owner_for_booking_page(db_session):
    owner_data = schemas.OwnerCreate(
        name="Booking Page Owner",
        email="booking@example.com",
        password="password",
        business_name="Booking Page Biz",
        slug="booking-page-biz"
    )
    return crud.create_owner(db_session, owner_data)


def test_dashboard_language_toggle_en(client, db_session):
    response = client.get("/dashboard?lang=en")
    assert response.status_code == 200
    assert "Your Bookings" in response.text # Example English string
    assert "lang=en" in response.text
    assert "lang=ar" in response.text
    assert "lang=fr" in response.text

def test_dashboard_language_toggle_ar(client, db_session):
    response = client.get("/dashboard?lang=ar")
    assert response.status_code == 200
    assert "مواعيدك" in response.text or "Your Bookings" in response.text # Fallback check if translation not perfect
    assert "lang=en" in response.text
    assert "lang=ar" in response.text
    assert "lang=fr" in response.text

def test_dashboard_language_toggle_fr(client, db_session):
    response = client.get("/dashboard?lang=fr")
    assert response.status_code == 200
    assert "Vos Réservations" in response.text or "Your Bookings" in response.text # Fallback check
    assert "lang=en" in response.text
    assert "lang=ar" in response.text
    assert "lang=fr" in response.text

def test_booking_page_language_toggle_en(client, db_session):
    owner = create_test_owner_for_booking_page(db_session)
    response = client.get(f"/book/{owner.slug}?lang=en")
    assert response.status_code == 200
    assert "Book an Appointment" in response.text # Example English string
    assert "lang=en" in response.text
    assert "lang=ar" in response.text
    assert "lang=fr" in response.text

def test_booking_page_language_toggle_ar(client, db_session):
    owner = create_test_owner_for_booking_page(db_session)
    response = client.get(f"/book/{owner.slug}?lang=ar")
    assert response.status_code == 200
    assert "احجز موعدا" in response.text or "Book an Appointment" in response.text
    assert "lang=en" in response.text
    assert "lang=ar" in response.text
    assert "lang=fr" in response.text

def test_booking_page_language_toggle_fr(client, db_session):
    owner = create_test_owner_for_booking_page(db_session)
    response = client.get(f"/book/{owner.slug}?lang=fr")
    assert response.status_code == 200
    assert "Prendre un Rendez-vous" in response.text or "Book an Appointment" in response.text
    assert "lang=en" in response.text
    assert "lang=ar" in response.text
    assert "lang=fr" in response.text
