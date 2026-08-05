import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.main import app, get_db, templates, i18n
from src.database import Base, get_db as get_db_original
from src.config import settings
import os
import shutil

# Override settings for testing
settings.TESTING = True
settings.DATABASE_URL = "sqlite:///./test_sql_app.db"
settings.SECRET_KEY = "test_secret_key_for_testing_only_this_should_be_long_enough"
settings.ACCESS_TOKEN_EXPIRE_MINUTES = 1

# Setup test database
TEST_DATABASE_URL = "sqlite:///./test_sql_app.db"
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(name="db_session")
def db_session_fixture():
    # Ensure test_sql_app.db is clean before each test
    if os.path.exists("./test_sql_app.db"):
        os.remove("./test_sql_app.db")
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine) # Clean up after tests
        if os.path.exists("./test_sql_app.db"):
            os.remove("./test_sql_app.db")

@pytest.fixture(name="client")
def client_fixture(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            db_session.close()
    app.dependency_overrides[get_db_original] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides = {} # Clean up overrides

@pytest.fixture(autouse=True)
def set_test_locale():
    # Ensure English locale is used for consistent testing unless specified
    i18n.set_locale('en')
    yield
    i18n.set_locale('en') # Reset after test

def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.text == "OK"

def test_root_redirects_to_login(client):
    response = client.get("/")
    assert response.status_code == 302
    assert response.headers["location"] == "/login"

def test_signup_page(client):
    response = client.get("/signup")
    assert response.status_code == 200
    assert "Create Your BookSlot Account" in response.text

def test_register_owner_success(client):
    response = client.post(
        "/signup",
        data={
            "name": "Test Owner",
            "email": "test@example.com",
            "password": "testpassword",
            "business_name": "Test Business",
            "slug": "test-business",
            "phone": "+1234567890"
        },
        follow_redirects=False
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/login"

def test_register_owner_duplicate_email(client):
    client.post(
        "/signup",
        data={
            "name": "Test Owner",
            "email": "duplicate@example.com",
            "password": "testpassword",
            "business_name": "Test Business",
            "slug": "unique-slug",
            "phone": "+1234567890"
        }
    )
    response = client.post(
        "/signup",
        data={
            "name": "Another Owner",
            "email": "duplicate@example.com",
            "password": "anotherpassword",
            "business_name": "Another Business",
            "slug": "another-slug",
            "phone": "+1234567891"
        }
    )
    assert response.status_code == 400
    assert "Email already registered" in response.text

def test_register_owner_duplicate_slug(client):
    client.post(
        "/signup",
        data={
            "name": "Test Owner",
            "email": "unique@example.com",
            "password": "testpassword",
            "business_name": "Test Business",
            "slug": "duplicate-slug",
            "phone": "+1234567890"
        }
    )
    response = client.post(
        "/signup",
        data={
            "name": "Another Owner",
            "email": "another@example.com",
            "password": "anotherpassword",
            "business_name": "Another Business",
            "slug": "duplicate-slug",
            "phone": "+1234567891"
        }
    )
    assert response.status_code == 400
    assert "Business URL already taken" in response.text

def test_login_page(client):
    response = client.get("/login")
    assert response.status_code == 200
    assert "Log In to Your BookSlot Account" in response.text

def test_login_success_and_dashboard_access(client):
    client.post(
        "/signup",
        data={
            "name": "Login Test Owner",
            "email": "login@example.com",
            "password": "loginpassword",
            "business_name": "Login Business",
            "slug": "login-business",
            "phone": "+1111111111"
        }
    )
    response = client.post(
        "/login",
        data={"username": "login@example.com", "password": "loginpassword"},
        follow_redirects=False
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/dashboard"
    
    # Check if access_token cookie is set
    assert "access_token" in response.cookies
    
    # Access dashboard with the cookie
    dashboard_response = client.get("/dashboard", cookies={"access_token": response.cookies["access_token"]})
    assert dashboard_response.status_code == 200
    assert "Login Business - Dashboard" in dashboard_response.text
    assert "Login Test Owner" in dashboard_response.text

def test_login_invalid_credentials(client):
    response = client.post(
        "/login",
        data={"username": "nonexistent@example.com", "password": "wrongpassword"}
    )
    assert response.status_code == 401
    assert "Incorrect email or password" in response.text

def test_logout(client):
    # First, log in to get a cookie
    client.post(
        "/signup",
        data={
            "name": "Logout Test Owner",
            "email": "logout@example.com",
            "password": "logoutpassword",
            "business_name": "Logout Business",
            "slug": "logout-business",
            "phone": "+2222222222"
        }
    )
    login_response = client.post(
        "/login",
        data={"username": "logout@example.com", "password": "logoutpassword"},
        follow_redirects=False
    )
    assert "access_token" in login_response.cookies

    # Now logout
    logout_response = client.get("/logout", cookies={"access_token": login_response.cookies["access_token"]}, follow_redirects=False)
    assert logout_response.status_code == 303
    assert logout_response.headers["location"] == "/login"
    assert "access_token" not in logout_response.cookies # Cookie should be cleared

def test_unauthorized_dashboard_access(client):
    response = client.get("/dashboard")
    assert response.status_code == 401
    assert "Could not validate credentials" in response.json()["detail"]

def test_public_booking_page_not_found(client):
    response = client.get("/non-existent-slug")
    assert response.status_code == 404
    assert "Owner not found" in response.text

def test_language_toggle(client):
    # Test initial language (default 'en')
    response = client.get("/login")
    assert "Log In to Your BookSlot Account" in response.text # English text
    assert 'lang="en"' in response.text # HTML lang attribute

    # Test setting to Arabic
    response = client.post("/set-language/ar", follow_redirects=False)
    assert response.status_code == 200
    assert response.cookies["lang"] == "ar"
    
    # Request login page again with Arabic cookie
    response_ar = client.get("/login", cookies={"lang": "ar"})
    assert "تسجيل الدخول إلى حسابك في بوك سلوت" in response_ar.text # Arabic text
    assert 'lang="ar"' in response_ar.text # HTML lang attribute

    # Test setting to French
    response = client.post("/set-language/fr", follow_redirects=False)
    assert response.status_code == 200
    assert response.cookies["lang"] == "fr"

    # Request login page again with French cookie
    response_fr = client.get("/login", cookies={"lang": "fr"})
    assert "Connectez-vous à votre compte BookSlot" in response_fr.text # French text
    assert 'lang="fr"' in response_fr.text # HTML lang attribute
