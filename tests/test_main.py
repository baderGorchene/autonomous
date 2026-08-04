import pytest
from httpx import AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.database import Base, get_db
from src.main import app
from src import crud, models, security, schemas
from src.config import settings
import json
from datetime import datetime, timedelta

settings.DATABASE_URL = "sqlite:///./test.db"
settings.TESTING = True
settings.SECRET_KEY = "test-secret-key"
settings.ACCESS_TOKEN_EXPIRE_MINUTES = 1

engine = create_engine(settings.DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(name="db_session")
def db_session_fixture():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

@pytest.fixture(name="client")
async def client_fixture(db_session: TestingSessionLocal):
    def override_get_db():
        try:
            yield db_session
        finally:
            db_session.close()

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client
    app.dependency_overrides = {}

@pytest.fixture
def test_owner_data():
    return {
        "name": "Test Owner",
        "email": "test@example.com",
        "password": "testpassword",
        "business_name": "Test Salon",
        "slug": "test-salon",
        "phone": "+1234567890"
    }

@pytest.fixture
def setup_owner(db_session: TestingSessionLocal, test_owner_data):
    owner_create = schemas.OwnerCreate(**test_owner_data)
    owner = crud.create_owner(db_session, owner_create)
    owner.services_json = json.dumps([
        {"name": "Haircut", "description": "Standard haircut", "price": 25.00, "duration_minutes": 30},
        {"name": "Massage", "description": "Relaxing massage", "price": 50.00, "duration_minutes": 60}
    ])
    owner.availability_json = json.dumps({
        "Monday": [{"start_time": "09:00", "end_time": "17:00"}],
        "Tuesday": [{"start_time": "09:00", "end_time": "17:00"}],
    })
    db_session.add(owner)
    db_session.commit()
    db_session.refresh(owner)
    return owner

@pytest.fixture
async def authenticated_client(client: AsyncClient, setup_owner):
    login_data = {"username": setup_owner.email, "password": "testpassword"}
    response = await client.post("/token", data=login_data)
    assert response.status_code == 200
    token = response.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    return client

@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    response = await client.get("/health")
    assert response.status_code == 200
    assert "BookSlot is healthy!" in response.text

@pytest.mark.asyncio
async def test_owner_signup_and_login(client: AsyncClient, test_owner_data):
    response = await client.get("/signup")
    assert response.status_code == 200
    assert "Sign Up for BookSlot" in response.text

    response = await client.post("/signup", data=test_owner_data)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"

    response = await client.post("/signup", data=test_owner_data)
    assert response.status_code == 400
    assert "Email already registered" in response.text

    login_data = {"username": test_owner_data["email"], "password": test_owner_data["password"]}
    response = await client.post("/token", data=login_data)
    assert response.status_code == 200
    assert "access_token" in response.json()

@pytest.mark.asyncio
async def test_owner_dashboard_access(authenticated_client: AsyncClient, setup_owner):
    response = await authenticated_client.get("/owner/dashboard")
    assert response.status_code == 200
    assert f"Welcome, {setup_owner.name}!" in response.text
    assert setup_owner.business_name in response.text
    assert "Haircut" in response.text

@pytest.mark.asyncio
async def test_owner_profile_update(authenticated_client: AsyncClient, setup_owner):
    new_name = "Updated Test Owner"
    new_business_name = "Updated Business"
    new_phone = "+9876543210"
    update_data = {
        "name": new_name,
        "business_name": new_business_name,
        "phone": new_phone
    }
    response = await authenticated_client.post("/owner/profile", data=update_data)
    assert response.status_code == 303
    assert response.headers["location"] == "/owner/dashboard"

    response = await authenticated_client.get("/owner/dashboard")
    assert response.status_code == 200
    assert new_name in response.text
    assert new_business_name in response.text
    assert new_phone in response.text

@pytest.mark.asyncio
async def test_public_booking_page(client: AsyncClient, setup_owner):
    response = await client.get(f"/{setup_owner.slug}")
    assert response.status_code == 200
    assert setup_owner.business_name in response.text
    assert "Book Your Appointment" in response.text
    assert "Haircut" in response.text

@pytest.mark.asyncio
async def test_booking_submission(client: AsyncClient, setup_owner):
    booking_date = (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')
    booking_data = {
        "customer_name": "Jane Doe",
        "customer_email": "jane@example.com",
        "customer_phone": "+1122334455",
        "service_name": "Haircut",
        "booking_date": booking_date,
        "booking_time": "10:00",
        "message": "Please be on time."
    }
    response = await client.post(f"/{setup_owner.slug}/book", data=booking_data)
    assert response.status_code == 200
    assert "Booking Confirmed!" in response.text
    assert "Jane Doe" in response.text
    assert "Haircut" in response.text

    login_data = {"username": setup_owner.email, "password": "testpassword"}
    login_response = await client.post("/token", data=login_data)
    token = login_response.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    dashboard_response = await client.get("/owner/dashboard")
    assert dashboard_response.status_code == 200
    assert "Jane Doe" in dashboard_response.text
    assert "10:00" in dashboard_response.text

@pytest.mark.asyncio
async def test_i18n_language_toggle(client: AsyncClient, setup_owner):
    response = await client.get(f"/{setup_owner.slug}")
    assert response.status_code == 200
    assert "Book Your Appointment" in response.text
    assert "Select Service" in response.text

    response = await client.get(f"/{setup_owner.slug}?lang=ar")
    assert response.status_code == 200
    assert "احجز موعدك" in response.text
    assert "اختر الخدمة" in response.text

    response = await client.get(f"/{setup_owner.slug}?lang=fr")
    assert response.status_code == 200
    assert "Réservez votre rendez-vous" in response.text
    assert "Sélectionner un service" in response.text

@pytest.mark.asyncio
async def test_currency_formatting_filter(client: AsyncClient, setup_owner):
    response = await client.get(f"/{setup_owner.slug}?lang=en")
    assert response.status_code == 200
    assert "$25.00" in response.text
    assert "$50.00" in response.text

    db = TestingSessionLocal()
    owner_from_db = crud.get_owner_by_slug(db, setup_owner.slug)
    services = json.loads(owner_from_db.services_json)
    services.append({"name": "Luxury Service", "description": "High-end service", "price": 1234.56, "duration_minutes": 120})
    owner_from_db.services_json = json.dumps(services)
    db.add(owner_from_db)
    db.commit()
    db.refresh(owner_from_db)
    db.close()

    response = await client.get(f"/{setup_owner.slug}?lang=ar")
    assert response.status_code == 200
    assert "25.00 ر.س" in response.text
    assert "50.00 ر.س" in response.text
    assert "1,234.56 ر.س" in response.text

    response = await client.get(f"/{setup_owner.slug}?lang=fr")
    assert response.status_code == 200
    assert "25,00 €" in response.text
    assert "50,00 €" in response.text
    assert "1 234,56 €" in response.text
