import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.main import app, get_db, create_tables
from src.database import Base
from src.config import settings
import os

# Override database URL for testing
settings.DATABASE_URL = "sqlite:///./test.db"
settings.TESTING = True

# Setup a test database
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db" # Use a distinct file for testing
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="module")
def setup_database():
    # Create tables
    Base.metadata.create_all(bind=engine)
    yield
    # Drop tables after tests
    Base.metadata.drop_all(bind=engine)
    # Clean up the test database file
    if os.path.exists("./test.db"):
        os.remove("./test.db")

@pytest.fixture(scope="function")
def db_session(setup_database):
    """Create a new database session for each test that rolls back after completion."""
    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)

    def override_get_db():
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    yield session
    transaction.rollback()
    connection.close()
    app.dependency_overrides = {} # Clear overrides

client = TestClient(app)

def test_health_check(db_session):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.text == "OK"

def test_root_page(db_session):
    response = client.get("/")
    assert response.status_code == 200
    assert "BookSlot" in response.text
    assert "Get Started - It's Free!" in response.text

def test_language_toggle_root(db_session):
    response = client.get("/?lang=ar")
    assert response.status_code == 200
    assert "بوكسلوت" in response.text # Check for Arabic text
    assert "Get Started - It's Free!" not in response.text # Ensure English is not present

    response = client.get("/?lang=fr")
    assert response.status_code == 200
    assert "BookSlot - Page de réservation simple" in response.text # Check for French text
    assert "BookSlot - Simple Booking Page" not in response.text # Ensure English is not present

def test_signup_page(db_session):
    response = client.get("/signup")
    assert response.status_code == 200
    assert "Sign Up" in response.text
    assert "Create your BookSlot account" in response.text

def test_login_page(db_session):
    response = client.get("/login")
    assert response.status_code == 200
    assert "Login" in response.text
    assert "Access your BookSlot dashboard" in response.text
