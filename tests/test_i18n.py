import pytest
import os
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.main import app, get_db
from src.database import Base
from src.models import Owner

# Setup a test database
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_bookslot_i18n.db" 
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="module", name="db_session")
def db_session_fixture_module():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    # Create a dummy owner for the booking page test
    dummy_owner = Owner(
        name="Test Owner",
        email="test@example.com",
        hashed_password="hashedpassword",
        business_name="Test Business",
        slug="test-business-slug",
        services_json=[],
        availability_json={}
    )
    db.add(dummy_owner)
    db.commit()
    db.refresh(dummy_owner)
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        if os.path.exists(SQLALCHEMY_DATABASE_URL.replace("sqlite:///", "")):
            os.remove(SQLALCHEMY_DATABASE_URL.replace("sqlite:///", ""))

@pytest.fixture(name="client")
def client_fixture(db_session_fixture_module):
    def override_get_db():
        yield db_session_fixture_module
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()

def test_i18n_booking_page_english(client):
    response = client.get("/book/test-business-slug?lang=en")
    assert response.status_code == 200
    assert b"Book an appointment" in response.content

def test_i18n_booking_page_arabic(client):
    response = client.get("/book/test-business-slug?lang=ar")
    assert response.status_code == 200
    assert b"\xd8\xa7\xd8\xad\xd8\xac\xd8\xb2 \xd9\x85\xd9\x88\xd8\xb9\xd8\xaf\xd8\xa7\xd9\x8b" in response.content

def test_i18n_booking_page_french(client):
    response = client.get("/book/test-business-slug?lang=fr")
    assert response.status_code == 200
    assert b"Prendre rendez-vous" in response.content