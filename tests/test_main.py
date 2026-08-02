import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.main import app, get_db # Import get_db from main to override it
from src.database import Base # Import Base from src.database
from src.config import settings

# Override database URL for testing to use an in-memory SQLite database
settings.DATABASE_URL = "sqlite:///:memory:"
settings.TESTING = True # Potentially useful for conditional logic in app

# Setup a test database engine and session
# Using connect_args={"check_same_thread": False} for SQLite
test_engine = create_engine(settings.DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

@pytest.fixture(name="db_session")
def db_session_fixture():
    """Fixture that provides a clean database session for each test."""
    # Create tables for the test database
    Base.metadata.create_all(bind=test_engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        # Drop tables after test to ensure a clean slate for the next test
        Base.metadata.drop_all(bind=test_engine)

@pytest.fixture(name="client")
def client_fixture(db_session):
    """Fixture that provides a TestClient for the FastAPI app with overridden dependencies."""
    def override_get_db():
        """Override the get_db dependency to use the test session."""
        try:
            yield db_session
        finally:
            # The session is closed by db_session_fixture's finally block
            pass 

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    # Clear overrides after the test to prevent interference with other tests or app runs
    app.dependency_overrides.clear()

def test_health_check(client):
    """Test the health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert "<h1>BookSlot Health Check: OK</h1>" in response.text

# Example test for the root redirect
def test_root_redirect_to_login(client):
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/owner/login"

# Example test for owner login page (GET)
def test_owner_login_page(client):
    response = client.get("/owner/login")
    assert response.status_code == 200
    # Assuming 'owner_login.html' contains this title or similar identifiable text
    assert "<h1>Owner Login</h1>" in response.text 
