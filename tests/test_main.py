import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.main import app # Assuming app is in src/main.py
from src.database import Base, get_db
from src.config import settings
import os

# --- Configuration for testing ---
# Ensure project_root is set correctly for tests to find templates/locales
# This is crucial if tests are run from a different working directory than the project root.
current_file_dir = os.path.dirname(os.path.abspath(__file__))
# Assuming 'tests' directory is at the same level as 'src'
project_root_for_tests = os.path.abspath(os.path.join(current_file_dir, os.pardir))
settings.PROJECT_ROOT = project_root_for_tests
settings.LOCALES_DIR = os.path.join(settings.PROJECT_ROOT, 'locales')

# Override DATABASE_URL for testing to use an in-memory SQLite database
settings.DATABASE_URL = "sqlite:///:memory:"
TEST_ENGINE = create_engine(settings.DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=TEST_ENGINE)

# --- Dependency Override ---
# Override get_db dependency to use the test database session
def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

# --- Pytest Fixtures ---
@pytest.fixture(name="client")
def client_fixture():
    """Provides a TestClient instance for making requests to the FastAPI app."""
    # Create tables for testing before each test function that uses this fixture
    Base.metadata.create_all(bind=TEST_ENGINE)
    with TestClient(app) as client:
        yield client
    # Drop tables after each test function that uses this fixture
    Base.metadata.drop_all(bind=TEST_ENGINE)

# --- Test Functions ---
def test_read_health(client):
    """Test the health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_root_endpoint_accessible(client):
    """Test if the root endpoint is accessible (e.g., serves a login/signup page or redirects)."""
    response = client.get("/")
    # Expecting a 200 for an HTML page or a redirect (307, 302)
    assert response.status_code in [200, 302, 307]
