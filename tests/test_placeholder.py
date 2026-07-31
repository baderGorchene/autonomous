import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.database import Base, get_db
from src.main import app
from src.config import settings
import os

# Override DATABASE_URL for testing to use an in-memory SQLite database
settings.DATABASE_URL = "sqlite:///./test.db" # Use a file-based for persistence during test run if needed, or :memory: for truly in-memory
settings.TESTING = True # Set testing flag

# Setup for SQLite in-memory database
# Use a file-based SQLite for now, as in-memory can be tricky with multiple test functions
# If issues persist, switch to in-memory with proper session management per test.
TEST_DATABASE_URL = "sqlite:///./test.db" 
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="module")
def client():
    # Create the database tables
    Base.metadata.create_all(bind=engine)
    
    # Override the get_db dependency to use the test database
    def override_get_db():
        try:
            db = TestingSessionLocal()
            yield db
        finally:
            db.close()
    
    app.dependency_overrides[get_db] = override_get_db
    
    with TestClient(app) as c:
        yield c
    
    # Drop tables after all tests are done in the module
    Base.metadata.drop_all(bind=engine)
    # Clean up the test database file
    if os.path.exists("./test.db"):
        os.remove("./test.db")

@pytest.fixture(scope="function")
def db_session(client):
    """Provides a fresh database session for each test function."""
    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)
    
    # Override get_db to use the session for the current test
    def override_get_db():
        try:
            yield session
        finally:
            session.close()
    
    app.dependency_overrides[get_db] = override_get_db
    yield session
    
    transaction.rollback() # Rollback changes after each test
    connection.close()

def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.text == "OK"

def test_owner_signup_and_login(client, db_session):
    # Test signup
    signup_data = {
        "name": "Test Owner",
        "email": "test@example.com",
        "password": "testpassword",
        "business_name": "Test Business",
        "slug": "test-business-slug",
        "phone": "+1234567890"
    }
    response = client.post("/signup", data=signup_data, follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/dashboard"
    assert "access_token" in response.cookies

    # Test login
    login_data = {
        "email": "test@example.com",
        "password": "testpassword"
    }
    response = client.post("/login", data=login_data, follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/dashboard"
    assert "access_token" in response.cookies

    # Check if owner exists in DB
    owner = db_session.query(models.Owner).filter(models.Owner.email == "test@example.com").first()
    assert owner is not None
    assert owner.name == "Test Owner"
    assert owner.slug == "test-business-slug"

def test_duplicate_email_signup(client, db_session):
    # First signup
    signup_data = {
        "name": "Owner One",
        "email": "duplicate@example.com",
        "password": "password",
        "business_name": "Business One",
        "slug": "business-one",
        "phone": "+111"
    }
    client.post("/signup", data=signup_data, follow_redirects=False)

    # Second signup with same email
    response = client.post("/signup", data=signup_data, follow_redirects=True) # follow_redirects to see error page
    assert response.status_code == 200 # Should render signup page with error
    assert "Email already registered" in response.text

def test_duplicate_slug_signup(client, db_session):
    # First signup
    signup_data_1 = {
        "name": "Owner A",
        "email": "owner_a@example.com",
        "password": "password",
        "business_name": "Business A",
        "slug": "unique-slug",
        "phone": "+111"
    }
    client.post("/signup", data=signup_data_1, follow_redirects=False)

    # Second signup with same slug
    signup_data_2 = {
        "name": "Owner B",
        "email": "owner_b@example.com",
        "password": "password",
        "business_name": "Business B",
        "slug": "unique-slug",
        "phone": "+222"
    }
    response = client.post("/signup", data=signup_data_2, follow_redirects=True)
    assert response.status_code == 200
    assert "Booking page URL (slug) already taken" in response.text
