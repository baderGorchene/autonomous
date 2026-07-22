import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.main import app, get_db
from src.database import Base
from src import models, crud, schemas, security
from datetime import datetime, timedelta

# Setup for test database
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
            pass 
    
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()

def create_test_owner(db_session):
    owner_data = schemas.OwnerCreate(
        name="Test Owner",
        email="test@example.com",
        password="testpassword",
        business_name="Test Business",
        slug="test-business-slug",
    )
    owner = crud.create_owner(db_session, owner_data)
    owner.services_json = [{"name": "Haircut", "duration": 30}] # Add a dummy service for booking page
    db_session.add(owner)
    db_session.commit()
    db_session.refresh(owner)
    return owner

def get_owner_token(client, email, password):
    response = client.post("/auth/token", data={"username": email, "password": password})
    assert response.status_code == 200, f"Failed to get token: {response.text}"
    return response.json()["access_token"]

def test_i18n_language_toggle_on_booking_page(client, db_session):
    owner = create_test_owner(db_session)
    
    # Test English
    response_en = client.get(f"/book/{owner.slug}?lang=en")
    assert response_en.status_code == 200
    assert "Book an appointment" in response_en.text
    assert "Service" in response_en.text
    assert "Customer Name" in response_en.text
    
    # Test Arabic
    response_ar = client.get(f"/book/{owner.slug}?lang=ar")
    assert response_ar.status_code == 200
    assert "احجز موعدا" in response_ar.text 
    assert "الخدمة" in response_ar.text
    assert "اسم العميل" in response_ar.text

    # Test French
    response_fr = client.get(f"/book/{owner.slug}?lang=fr")
    assert response_fr.status_code == 200
    assert "Prendre rendez-vous" in response_fr.text
    assert "Service" in response_fr.text 
    assert "Nom du client" in response_fr.text

def test_i18n_language_toggle_on_dashboard_page(client, db_session):
    owner = create_test_owner(db_session)
    token = get_owner_token(client, owner.email, "testpassword")

    headers = {"Authorization": f"Bearer {token}"}

    # Test English
    response_en = client.get("/dashboard?lang=en", headers=headers)
    assert response_en.status_code == 200
    assert "Dashboard" in response_en.text
    assert "Upcoming Bookings" in response_en.text
    assert "Profile" in response_en.text

    # Test Arabic
    response_ar = client.get("/dashboard?lang=ar", headers=headers)
    assert response_ar.status_code == 200
    assert "لوحة التحكم" in response_ar.text 
    assert "الحجوزات القادمة" in response_ar.text
    assert "الملف الشخصي" in response_ar.text

    # Test French
    response_fr = client.get("/dashboard?lang=fr", headers=headers)
    assert response_fr.status_code == 200
    assert "Tableau de bord" in response_fr.text
    assert "Réservations à venir" in response_fr.text
    assert "Profil" in response_fr.text
