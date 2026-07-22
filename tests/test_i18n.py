import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.main import app, get_db
from src.database import Base
from src import crud, schemas, security
from datetime import timedelta

# Setup for testing database
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
    app.dependency_overrides = {} # Clear overrides

@pytest.fixture
def test_owner(db_session):
    owner_data = schemas.OwnerCreate(
        name="Test Owner",
        email="test@example.com",
        password="testpassword",
        business_name="Test Business",
        slug="test-business"
    )
    owner = crud.create_owner(db_session, owner_data)
    return owner

@pytest.fixture
def owner_access_token(test_owner):
    access_token_expires = timedelta(minutes=security.ACCESS_TOKEN_EXPIRE_MINUTES)
    return security.create_access_token(
        data={"sub": test_owner.email}, expires_delta=access_token_expires
    )

def test_language_toggle_on_dashboard(client, test_owner, owner_access_token):
    headers = {"Authorization": f"Bearer {owner_access_token}"}

    # Test English dashboard
    response_en = client.get("/dashboard?lang=en", headers=headers)
    assert response_en.status_code == 200
    assert "Upcoming Bookings" in response_en.text
    assert "Profile" in response_en.text

    # Test Arabic dashboard
    response_ar = client.get("/dashboard?lang=ar", headers=headers)
    assert response_ar.status_code == 200
    assert ("المواعيد القادمة" in response_ar.text or "الحجوزات القادمة" in response_ar.text)
    assert "الملف الشخصي" in response_ar.text

    # Test French dashboard
    response_fr = client.get("/dashboard?lang=fr", headers=headers)
    assert response_fr.status_code == 200
    assert "Rendez-vous à venir" in response_fr.text
    assert "Profil" in response_fr.text

def test_language_toggle_on_booking_page(client, db_session, test_owner):
    # Test English booking page
    response_en = client.get(f"/book/{test_owner.slug}?lang=en")
    assert response_en.status_code == 200
    assert "Book your slot" in response_en.text
    assert "Customer Name" in response_en.text

    # Test Arabic booking page
    response_ar = client.get(f"/book/{test_owner.slug}?lang=ar")
    assert response_ar.status_code == 200
    assert ("احجز موعدك" in response_ar.text or "احجز مكانك" in response_ar.text)
    assert "اسم العميل" in response_ar.text

    # Test French booking page
    response_fr = client.get(f"/book/{test_owner.slug}?lang=fr")
    assert response_fr.status_code == 200
    assert "Réservez votre créneau" in response_fr.text
    assert "Nom du client" in response_fr.text