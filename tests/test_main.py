import pytest
from httpx import AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.database import Base, get_db
from src.main import app # Import the FastAPI app
from src.config import settings
import json
import os

# Override database URL for testing
settings.DATABASE_URL = "sqlite:///./test.db"
settings.TESTING = True

# Setup a test database
engine = create_engine(settings.DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(name="db_session")
def db_session_fixture():
    Base.metadata.drop_all(bind=engine) # Drop tables for a clean slate
    Base.metadata.create_all(bind=engine) # Create tables
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine) # Clean up after tests
        # Ensure the test.db file is removed
        if os.path.exists("./test.db"):
            os.remove("./test.db")

@pytest.fixture(name="client")
async def client_fixture(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            db_session.close()

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()

@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    response = await client.get("/health")
    assert response.status_code == 200
    assert "BookSlot is running!" in response.text

@pytest.mark.asyncio
async def test_signup_and_login(client: AsyncClient):
    # Test Signup
    signup_data = {
        "name": "Test Owner",
        "email": "test@example.com",
        "password": "testpassword",
        "business_name": "Test Business",
        "slug": "test-business-slug",
        "phone": "+1234567890"
    }
    response = await client.post("/signup", data=signup_data)
    assert response.status_code == 303 # Redirect to dashboard
    assert response.headers["location"] == "/dashboard"

    # Extract access token from cookie
    cookies = client.cookies
    assert "access_token" in cookies
    
    # Test Login (using the created user)
    login_data = {
        "username": "test@example.com",
        "password": "testpassword"
    }
    response = await client.post("/login", data=login_data)
    assert response.status_code == 303
    assert response.headers["location"] == "/dashboard"
    assert "access_token" in client.cookies # Cookie should be set again

@pytest.mark.asyncio
async def test_dashboard_access_authenticated(client: AsyncClient):
    # First, sign up and log in to get an authenticated session
    signup_data = {
        "name": "Dash Owner",
        "email": "dash@example.com",
        "password": "dashpassword",
        "business_name": "Dash Business",
        "slug": "dash-business-slug",
        "phone": "+1112223333"
    }
    await client.post("/signup", data=signup_data)

    response = await client.get("/dashboard")
    assert response.status_code == 200
    assert "Dash Owner" in response.text
    assert "Dash Business" in response.text
    assert "No upcoming bookings." in response.text

@pytest.mark.asyncio
async def test_public_booking_page_display(client: AsyncClient, db_session):
    # Create an owner with services and availability
    owner = models.Owner(
        name="Bookable Owner",
        email="book@example.com",
        hashed_password="hashedpassword", # Not used for public page, but needed for model
        business_name="Bookable Business",
        slug="bookable-business",
        phone="+1234567890",
        services_json=json.dumps([{"name": "Consultation", "duration_minutes": 60, "price": 100.00}]),
        availability_json=json.dumps({"weekly_availability": [{"day_of_week": 0, "start_time": "09:00", "end_time": "17:00"}]})
    )
    db_session.add(owner)
    db_session.commit()
    db_session.refresh(owner)

    response = await client.get("/book/bookable-business")
    assert response.status_code == 200
    assert "Bookable Business" in response.text
    assert "Consultation" in response.text
    assert "100.00" in response.text # Raw price should be present before formatting

@pytest.mark.asyncio
async def test_booking_submission_and_confirmation(client: AsyncClient, db_session):
    owner = models.Owner(
        name="Book Owner",
        email="book2@example.com",
        hashed_password="hashedpassword",
        business_name="Book Business",
        slug="book-business",
        phone="+1234567890",
        services_json=json.dumps([{"name": "Therapy", "duration_minutes": 45, "price": 80.00}]),
        availability_json=json.dumps({"weekly_availability": [{"day_of_week": 0, "start_time": "09:00", "end_time": "17:00"}]})
    )
    db_session.add(owner)
    db_session.commit()
    db_session.refresh(owner)

    booking_data = {
        "customer_name": "Jane Doe",
        "customer_email": "jane@example.com",
        "customer_phone": "+1987654321",
        "service_name": "Therapy",
        "booking_date": "2024-06-01", # Assuming a future date where Monday (0) is available
        "booking_time": "10:00-10:45"
    }
    response = await client.post("/book/book-business", data=booking_data)
    assert response.status_code == 200 # Should return confirmation page
    assert "Booking Confirmed!" in response.text
    assert "Jane Doe" in response.text
    assert "Therapy" in response.text

    # Verify booking in DB
    bookings = db_session.query(models.Booking).filter(models.Booking.owner_id == owner.id).all()
    assert len(bookings) == 1
    assert bookings[0].customer_name == "Jane Doe"
    assert bookings[0].service_name == "Therapy"

@pytest.mark.asyncio
async def test_i18n_language_toggle(client: AsyncClient):
    response_en = await client.get("/login?lang=en")
    assert response_en.status_code == 200
    assert "Login to BookSlot" in response_en.text
    
    response_ar = await client.get("/login?lang=ar")
    assert response_ar.status_code == 200
    assert "تسجيل الدخول إلى BookSlot" in response_ar.text # Arabic translation
    
    response_fr = await client.get("/login?lang=fr")
    assert response_fr.status_code == 200
    assert "Se connecter à BookSlot" in response_fr.text # French translation

@pytest.mark.asyncio
async def test_currency_formatting_arabic(client: AsyncClient, db_session):
    owner = models.Owner(
        name="Currency Owner",
        email="currency@example.com",
        hashed_password="hashedpassword",
        business_name="Currency Business",
        slug="currency-business",
        phone="+1234567890",
        services_json=json.dumps([{"name": "Service A", "duration_minutes": 30, "price": 1234.56}]),
        availability_json=json.dumps({}) # Not relevant for this test
    )
    db_session.add(owner)
    db_session.commit()
    db_session.refresh(owner)

    response = await client.get("/book/currency-business?lang=ar")
    assert response.status_code == 200
    # Check for Arabic currency format: 1,234.56 ر.س
    # The filter uses \u0631.\u0633 for 'ر.س'
    assert "1,234.56 \u0631.\u0633" in response.text

@pytest.mark.asyncio
async def test_currency_formatting_french(client: AsyncClient, db_session):
    owner = models.Owner(
        name="Currency Owner FR",
        email="currencyfr@example.com",
        hashed_password="hashedpassword",
        business_name="Currency Business FR",
        slug="currency-business-fr",
        phone="+1234567890",
        services_json=json.dumps([{"name": "Service B", "duration_minutes": 30, "price": 9876.54}]),
        availability_json=json.dumps({})
    )
    db_session.add(owner)
    db_session.commit()
    db_session.refresh(owner)

    response = await client.get("/book/currency-business-fr?lang=fr")
    assert response.status_code == 200
    # Check for French currency format: 9 876,54 €
    assert "9 876,54 \u20ac" in response.text

@pytest.mark.asyncio
async def test_currency_formatting_english(client: AsyncClient, db_session):
    owner = models.Owner(
        name="Currency Owner EN",
        email="currencyen@example.com",
        hashed_password="hashedpassword",
        business_name="Currency Business EN",
        slug="currency-business-en",
        phone="+1234567890",
        services_json=json.dumps([{"name": "Service C", "duration_minutes": 30, "price": 50.75}]),
        availability_json=json.dumps({})
    )
    db_session.add(owner)
    db_session.commit()
    db_session.refresh(owner)

    response = await client.get("/book/currency-business-en?lang=en")
    assert response.status_code == 200
    # Check for English currency format: $50.75
    assert "$50.75" in response.text
