import pytest
from httpx import AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.main import app, get_db
from src.database import Base
from src.models import Owner, Booking
from src.security import get_password_hash, create_access_token
from datetime import timedelta, datetime, date
from src.config import settings

# Use an in-memory SQLite database for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Override the get_db dependency to use the testing database
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
async def client_fixture(db_session):
    def override_get_db():
        yield db_session
    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client
    app.dependency_overrides = {}

@pytest.fixture
def test_owner(db_session):
    hashed_password = get_password_hash("testpassword")
    owner = Owner(
        name="Test Owner",
        email="test@example.com",
        hashed_password=hashed_password,
        business_name="Test Business",
        slug="test-business",
        phone="+15551234567",
        services_json='[{"name": "Haircut", "duration": 30, "price": 25.0}]',
        availability_json='{"0": [{"start_time": "09:00", "end_time": "17:00"}]}'
    )
    db_session.add(owner)
    db_session.commit()
    db_session.refresh(owner)
    return owner

@pytest.fixture
def auth_token(test_owner):
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return create_access_token(
        data={"sub": test_owner.email}, expires_delta=access_token_expires
    )

# --- Health Check Tests ---
async def test_health_check(client: AsyncClient):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

# --- Authentication & Registration Tests ---
async def test_register_page(client: AsyncClient):
    response = await client.get("/register")
    assert response.status_code == 200
    assert "Register" in response.text

async def test_register_owner(client: AsyncClient):
    response = await client.post(
        "/register",
        data={
            "name": "New Owner",
            "email": "new@example.com",
            "password": "newpassword",
            "business_name": "New Business",
            "slug": "new-business"
        },
        follow_redirects=False
    )
    assert response.status_code == 302
    assert response.headers["location"] == "/login"

async def test_register_owner_duplicate_email(client: AsyncClient, test_owner: Owner):
    response = await client.post(
        "/register",
        data={
            "name": "Another Owner",
            "email": "test@example.com", # Duplicate email
            "password": "anotherpassword",
            "business_name": "Another Business",
            "slug": "another-business"
        }
    )
    assert response.status_code == 200 # Renders with error on same page
    assert "Email already registered" in response.text

async def test_register_owner_duplicate_slug(client: AsyncClient, test_owner: Owner):
    response = await client.post(
        "/register",
        data={
            "name": "Another Owner",
            "email": "another@example.com",
            "password": "anotherpassword",
            "business_name": "Another Business",
            "slug": "test-business" # Duplicate slug
        }
    )
    assert response.status_code == 200 # Renders with error on same page
    assert "Business URL (slug) already taken" in response.text

async def test_login_page(client: AsyncClient):
    response = await client.get("/login")
    assert response.status_code == 200
    assert "Login" in response.text

async def test_login_success(client: AsyncClient, test_owner: Owner):
    response = await client.post(
        "/login",
        data={
            "email": test_owner.email,
            "password": "testpassword"
        },
        follow_redirects=False
    )
    assert response.status_code == 302
    assert response.headers["location"] == "/dashboard"
    assert "access_token" in response.cookies

async def test_login_failure(client: AsyncClient):
    response = await client.post(
        "/login",
        data={
            "email": "nonexistent@example.com",
            "password": "wrongpassword"
        }
    )
    assert response.status_code == 200
    assert "Incorrect email or password" in response.text

# --- Dashboard Tests ---
async def test_dashboard_access_unauthenticated(client: AsyncClient):
    response = await client.get("/dashboard", follow_redirects=False)
    assert response.status_code == 307 # Redirect to login or unauthorized

async def test_dashboard_access_authenticated(client: AsyncClient, auth_token: str):
    response = await client.get(
        "/dashboard",
        cookies={"access_token": auth_token}
    )
    assert response.status_code == 200
    assert "Dashboard" in response.text
    assert "Test Owner" in response.text

async def test_update_profile(client: AsyncClient, auth_token: str, test_owner: Owner):
    new_services = json.dumps([{"name": "Haircut", "duration": 30, "price": 25.0}, {"name": "Manicure", "duration": 60, "price": 40.0}])
    new_availability = json.dumps('{"1": [{"start_time": "08:00", "end_time": "16:00"}]}')

    response = await client.post(
        "/dashboard/profile",
        cookies={"access_token": auth_token},
        data={
            "name": "Updated Owner Name",
            "business_name": "Updated Business Name",
            "phone": "+19876543210",
            "services_json": new_services,
            "availability_json": new_availability
        },
        follow_redirects=False
    )
    assert response.status_code == 302
    assert response.headers["location"] == "/dashboard?success=profile_updated"

    # Verify update in DB
    db = TestingSessionLocal()
    updated_owner = db.query(Owner).filter(Owner.id == test_owner.id).first()
    db.close()
    assert updated_owner.name == "Updated Owner Name"
    assert updated_owner.business_name == "Updated Business Name"
    assert updated_owner.phone == "+19876543210"
    assert updated_owner.services_json == new_services
    assert updated_owner.availability_json == new_availability

# --- Public Booking Page Tests ---
async def test_booking_page_exists(client: AsyncClient, test_owner: Owner):
    response = await client.get(f"/book/{test_owner.slug}")
    assert response.status_code == 200
    assert "Book Slot" in response.text
    assert test_owner.business_name in response.text

async def test_booking_page_not_found(client: AsyncClient):
    response = await client.get("/book/nonexistent-business")
    assert response.status_code == 404
    assert "Owner not found" in response.text

# --- Booking Submission Tests ---
async def test_submit_booking_success(client: AsyncClient, test_owner: Owner, mocker):
    # Mock notification functions
    mocker.patch('src.notifications.send_email_confirmation', return_value=True)
    mocker.patch('src.notifications.send_whatsapp_confirmation', return_value=True)

    booking_date = (date.today() + timedelta(days=7)).strftime("%Y-%m-%d")

    response = await client.post(
        f"/book/{test_owner.slug}/submit",
        data={
            "customer_name": "Jane Doe",
            "customer_email": "jane@example.com",
            "customer_phone": "+15559876543",
            "service_name": "Haircut",
            "booking_date_str": booking_date,
            "booking_time": "09:00"
        }
    )
    assert response.status_code == 200 # Should render confirmation page
    assert "Booking Confirmed" in response.text
    assert "Jane Doe" in response.text
    assert 'src.notifications.send_email_confirmation'.called # Verify email was attempted
    assert 'src.notifications.send_whatsapp_confirmation'.called # Verify WhatsApp was attempted

    # Verify booking in DB
    db = TestingSessionLocal()
    booking = db.query(Booking).filter_by(customer_email="jane@example.com").first()
    db.close()
    assert booking is not None
    assert booking.service_name == "Haircut"

async def test_submit_booking_invalid_date(client: AsyncClient, test_owner: Owner):
    response = await client.post(
        f"/book/{test_owner.slug}/submit",
        data={
            "customer_name": "Jane Doe",
            "customer_email": "jane@example.com",
            "service_name": "Haircut",
            "booking_date_str": "invalid-date", # Invalid date format
            "booking_time": "09:00"
        }
    )
    assert response.status_code == 400
    assert "Invalid date format." in response.text

async def test_submit_booking_past_date(client: AsyncClient, test_owner: Owner):
    past_date = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    response = await client.post(
        f"/book/{test_owner.slug}/submit",
        data={
            "customer_name": "Jane Doe",
            "customer_email": "jane@example.com",
            "service_name": "Haircut",
            "booking_date_str": past_date,
            "booking_time": "09:00"
        }
    )
    assert response.status_code == 400
    assert "Cannot book in the past." in response.text

# --- I18n Tests ---
async def test_language_toggle(client: AsyncClient):
    # Default language should be English
    response = await client.get("/login")
    assert "Login" in response.text

    # Switch to Arabic
    response = await client.get("/lang/ar", follow_redirects=False)
    assert response.status_code == 302
    assert response.cookies['session'] # Session cookie should be set

    response = await client.get("/login", cookies=response.cookies)
    assert "تسجيل الدخول" in response.text # Check for Arabic translation

    # Switch to French
    response = await client.get("/lang/fr", follow_redirects=False, cookies=response.cookies)
    assert response.status_code == 302

    response = await client.get("/login", cookies=response.cookies)
    assert "Connexion" in response.text # Check for French translation

    # Switch back to English
    response = await client.get("/lang/en", follow_redirects=False, cookies=response.cookies)
    response = await client.get("/login", cookies=response.cookies)
    assert "Login" in response.text
