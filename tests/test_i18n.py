import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.main import app, get_db
from src.database import Base
from src import models, crud, schemas
from datetime import datetime
import json

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
        try:
            yield db_session
        finally:
            db_session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides = {} # Clean up overrides

@pytest.fixture
def setup_owner(db_session: TestingSessionLocal):
    owner_data = schemas.OwnerCreate(
        name="Test Owner",
        email="test@example.com",
        password="testpassword",
        business_name="Test Business",
        slug="test-business",
    )
    owner = crud.create_owner(db_session, owner_data)
    owner.services_json = json.dumps([{"name": "Haircut", "duration": 30}])
    owner.availability_json = json.dumps({
        "monday": ["09:00-17:00"]
    })
    db_session.add(owner)
    db_session.commit()
    db_session.refresh(owner)
    return owner

def test_booking_page_i18n_english(client: TestClient, setup_owner: models.Owner):
    response = client.get(f"/book/{setup_owner.slug}?lang=en")
    assert response.status_code == 200
    assert "Book an Appointment" in response.text
    assert "Your Name" in response.text
    assert "Select Service" in response.text
    assert "Book Now" in response.text

def test_booking_page_i18n_arabic(client: TestClient, setup_owner: models.Owner):
    response = client.get(f"/book/{setup_owner.slug}?lang=ar")
    assert response.status_code == 200
    assert "احجز موعدًا" in response.text # "Book an Appointment"
    assert "اسمك" in response.text # "Your Name"
    assert "اختر الخدمة" in response.text # "Select Service"
    assert "احجز الآن" in response.text # "Book Now"

def test_booking_page_i18n_french(client: TestClient, setup_owner: models.Owner):
    response = client.get(f"/book/{setup_owner.slug}?lang=fr")
    assert response.status_code == 200
    assert "Prendre un rendez-vous" in response.text # "Book an Appointment"
    assert "Votre Nom" in response.text # "Your Name"
    assert "Sélectionner un Service" in response.text # "Select Service"
    assert "Réserver Maintenant" in response.text # "Book Now"