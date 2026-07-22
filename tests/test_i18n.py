import pytest
import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.main import app as fastapi_app, get_db
from src.database import Base
from src import models, schemas, crud, security
from src.config import settings
from jose import jwt
from datetime import datetime, timedelta

# --- Test Database Setup ---
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_i18n.db"

test_engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

fastapi_app.dependency_overrides[get_db] = override_get_db

@pytest.fixture(name="db_session")
def db_session_fixture():
    Base.metadata.create_all(bind=test_engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=test_engine)

# --- HTTPX Client Fixture ---
@pytest.fixture(name="client")
async def client_fixture(db_session):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=fastapi_app), base_url="http://test") as client:
        yield client

# --- Authentication Fixtures ---
def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

@pytest.fixture(name="owner_data")
def owner_data_fixture():
    return {
        "name": "Test Owner",
        "email": "test@example.com",
        "password": "testpassword",
        "business_name": "Test Business",
        "slug": "test-business",
        "phone": "1234567890"
    }

@pytest.fixture(name="test_owner")
def test_owner_fixture(db_session, owner_data):
    owner_schema = schemas.OwnerCreate(**owner_data)
    owner = crud.create_owner(db_session, owner_schema)
    # Manually update services_json and availability_json for the slug page to work
    owner.services_json = [{"name": "Consultation", "duration": 30, "price": 50}]
    owner.availability_json = {"monday": [{"start": "09:00", "end": "17:00"}]}
    db_session.add(owner)
    db_session.commit()
    db_session.refresh(owner)
    return owner

@pytest.fixture(name="auth_headers")
def auth_headers_fixture(test_owner):
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": test_owner.email}, expires_delta=access_token_expires
    )
    return {"Authorization": f"Bearer {access_token}"}

# --- I18n Tests for Dashboard Page ---
@pytest.mark.asyncio
async def test_dashboard_language_toggle_en(client, auth_headers):
    response = await client.get("/dashboard?lang=en", headers=auth_headers)
    assert response.status_code == 200
    assert "Dashboard" in response.text
    assert "Upcoming Bookings" in response.text

@pytest.mark.asyncio
async def test_dashboard_language_toggle_ar(client, auth_headers):
    response = await client.get("/dashboard?lang=ar", headers=auth_headers)
    assert response.status_code == 200
    assert "لوحة التحكم" in response.text
    assert "الحجوزات القادمة" in response.text

@pytest.mark.asyncio
async def test_dashboard_language_toggle_fr(client, auth_headers):
    response = await client.get("/dashboard?lang=fr", headers=auth_headers)
    assert response.status_code == 200
    assert "Tableau de bord" in response.text
    assert "Prochaines réservations" in response.text

# --- I18n Tests for Booking Page ---
@pytest.mark.asyncio
async def test_booking_page_language_toggle_en(client, test_owner):
    response = await client.get(f"/book/{test_owner.slug}?lang=en")
    assert response.status_code == 200
    assert "Book an Appointment" in response.text
    assert "Your Name" in response.text

@pytest.mark.asyncio
async def test_booking_page_language_toggle_ar(client, test_owner):
    response = await client.get(f"/book/{test_owner.slug}?lang=ar")
    assert response.status_code == 200
    assert "احجز موعدًا" in response.text
    assert "اسمك" in response.text

@pytest.mark.asyncio
async def test_booking_page_language_toggle_fr(client, test_owner):
    response = await client.get(f"/book/{test_owner.slug}?lang=fr")
    assert response.status_code == 200
    assert "Réserver un rendez-vous" in response.text
    assert "Votre nom" in response.text
