import pytest
from httpx import AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.main import app, get_db
from src.database import Base
from src.models import Owner
from src.security import create_access_token
from datetime import timedelta
import os

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
        # Ensure the test database file is removed after tests
        if os.path.exists("./test.db"): 
            os.remove("./test.db")

@pytest.fixture(name="client")
async def client_fixture(db_session):
    def override_get_db():
        yield db_session
    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()

@pytest.fixture
def test_owner(db_session):
    from src.security import get_password_hash
    owner = Owner(
        name="Test Owner",
        email="test@example.com",
        hashed_password=get_password_hash("testpassword"),
        business_name="Test Business",
        slug="test-business",
        services_json=[],
        availability_json={},
        phone="1234567890"
    )
    db_session.add(owner)
    db_session.commit()
    db_session.refresh(owner)
    return owner

@pytest.fixture
def authenticated_client(client, test_owner):
    access_token_expires = timedelta(minutes=30)
    access_token = create_access_token(
        data={"sub": test_owner.email}, expires_delta=access_token_expires
    )
    client.headers = {"Authorization": f"Bearer {access_token}"}
    return client

@pytest.mark.asyncio
async def test_dashboard_i18n_english(authenticated_client):
    response = await authenticated_client.get("/dashboard?lang=en")
    assert response.status_code == 200
    assert "<h1>Dashboard</h1>" in response.text
    assert "Upcoming Bookings" in response.text

@pytest.mark.asyncio
async def test_dashboard_i18n_arabic(authenticated_client):
    response = await authenticated_client.get("/dashboard?lang=ar")
    assert response.status_code == 200
    assert "<h1>لوحة القيادة</h1>" in response.text
    assert "الحجوزات القادمة" in response.text

@pytest.mark.asyncio
async def test_dashboard_i18n_french(authenticated_client):
    response = await authenticated_client.get("/dashboard?lang=fr")
    assert response.status_code == 200
    assert "<h1>Tableau de bord</h1>" in response.text
    assert "Réservations à venir" in response.text

@pytest.mark.asyncio
async def test_booking_page_i18n_english(client, test_owner):
    response = await client.get(f"/book/{test_owner.slug}?lang=en")
    assert response.status_code == 200
    assert "Book a Slot with" in response.text
    assert "Your Name" in response.text

@pytest.mark.asyncio
async def test_booking_page_i18n_arabic(client, test_owner):
    response = await client.get(f"/book/{test_owner.slug}?lang=ar")
    assert response.status_code == 200
    assert "احجز موعدا مع" in response.text
    assert "اسمك" in response.text

@pytest.mark.asyncio
async def test_booking_page_i18n_french(client, test_owner):
    response = await client.get(f"/book/{test_owner.slug}?lang=fr")
    assert response.status_code == 200
    assert "Réserver un créneau avec" in response.text
    assert "Votre nom" in response.text
