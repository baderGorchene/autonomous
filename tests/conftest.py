import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.main import app # Assuming src.main is the main FastAPI app
from src.database import Base, get_db
from fastapi.testclient import TestClient
from src.config import settings

# Use an in-memory SQLite database for testing
TEST_DATABASE_URL = "sqlite:///:memory:"

@pytest.fixture(name="test_db_engine")
def test_db_engine_fixture():
    """Fixture for the test database engine."""
    engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine) # Create tables
    yield engine
    Base.metadata.drop_all(bind=engine) # Drop tables after tests

@pytest.fixture(name="test_db_session")
def test_db_session_fixture(test_db_engine):
    """Fixture for a test database session."""
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_db_engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

@pytest.fixture(name="override_get_db")
def override_get_db_fixture(test_db_session):
    """Fixture to override the get_db dependency for tests."""
    def _override_get_db():
        yield test_db_session
    app.dependency_overrides[get_db] = _override_get_db
    yield
    app.dependency_overrides.pop(get_db)

@pytest.fixture(name="client")
def client_fixture(override_get_db):
    """Fixture for a test client."""
    # Temporarily set TESTING to True for the duration of tests
    original_testing_setting = settings.TESTING
    settings.TESTING = True
    with TestClient(app) as c:
        yield c
    settings.TESTING = original_testing_setting # Restore original setting
