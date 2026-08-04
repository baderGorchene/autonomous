import pytest
from httpx import AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.main import app
from src.database import Base, get_db
from src.config import settings
import asyncio
import os

# Override database settings for testing
settings.DATABASE_URL = "sqlite:///./test.db"
settings.TESTING = True

# Setup a test database
engine = create_engine(settings.DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(name="db_session")
def db_session_fixture():
    """Create a clean database session for each test."""
    Base.metadata.create_all(bind=engine) # Create tables
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine) # Drop tables after test

@pytest.fixture(name="client")
async def client_fixture(db_session):
    """Create an httpx client for testing FastAPI app."""
    def override_get_db():
        yield db_session
    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client
    app.dependency_overrides = {} # Clean up overrides

@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

@pytest.mark.asyncio
async def test_root_redirect_to_signup(client: AsyncClient):
    response = await client.get("/", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/signup"

@pytest.mark.asyncio
async def test_signup_page(client: AsyncClient):
    response = await client.get("/signup")
    assert response.status_code == 200
    assert "Sign Up - BookSlot" in response.text
    assert "Your Name" in response.text

@pytest.mark.asyncio
async def test_owner_signup_and_login(client: AsyncClient):
    # Test Signup
    signup_data = {
        "name": "Test Owner",
        "email": "test@example.com",
        "password": "testpassword",
        "business_name": "Test Business",
        "slug": "test-business",
        "phone": "+1234567890"
    }
    response = await client.post("/signup", data=signup_data, follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/login?lang=en"

    # Test Login
    login_data = {
        "username": "test@example.com",
        "password": "testpassword"
    }
    response = await client.post("/token", data=login_data, follow_redirects=False)
    assert response.status_code == 200
    assert "access_token" in response.json()
    assert "token_type" in response.json()

@pytest.mark.asyncio
async def test_i18n_language_toggle_on_signup(client: AsyncClient):
    response_en = await client.get("/signup?lang=en")
    assert "Sign Up" in response_en.text
    assert "Already have an account? Log In" in response_en.text

    response_ar = await client.get("/signup?lang=ar")
    assert "التسجيل" in response_ar.text
    assert "هل لديك حساب بالفعل؟ تسجيل الدخول" in response_ar.text

    response_fr = await client.get("/signup?lang=fr")
    assert "S'inscrire" in response_fr.text
    assert "Déjà un compte ? Se connecter" in response_fr.text

@pytest.mark.asyncio
async def test_currency_formatting_on_booking_page(client: AsyncClient, db_session):
    # First, create an owner to have a booking page
    owner_data = {
        "name": "Currency Test Owner",
        "email": "currency@example.com",
        "password": "securepassword",
        "business_name": "Currency Clinic",
        "slug": "currency-clinic",
        "phone": "+1234567890"
    }
    await client.post("/signup", data=owner_data) # Signup the owner

    # Access booking page with different languages and check currency format
    response_en = await client.get("/book/currency-clinic?lang=en")
    assert response_en.status_code == 200
    assert "$50.00" in response_en.text # Default service price in English

    response_ar = await client.get("/book/currency-clinic?lang=ar")
    assert response_ar.status_code == 200
    # The Arabic currency filter returns "50.00 ر.س"
    assert "50.00 \u0631.\u0633" in response_ar.text.replace('&#x200f;', '').replace('&#x200e;', '') # Remove potential RTL marks

    response_fr = await client.get("/book/currency-clinic?lang=fr")
    assert response_fr.status_code == 200
    assert "50,00 \u20ac" in response_fr.text