import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.database import Base, get_db
from src.main import app
from src.config import settings
from fastapi.testclient import TestClient
import os

# Override database URL for testing
settings.DATABASE_URL = "sqlite:///./test.db" # Use a file-based SQLite for better isolation across tests if needed
# Or, for in-memory, if issues arise with concurrent access, ensure proper session management:
# settings.DATABASE_URL = "sqlite:///:memory:"
settings.TESTING = True

# Setup test engine and session
test_engine = create_engine(settings.DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

# Override the get_db dependency to use the test database
@pytest.fixture(name="db_session")
def db_session_fixture():
    # Ensure a clean database for each test
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        # For file-based SQLite, clean up the file after all tests if necessary
        # if os.path.exists("./test.db"): os.remove("./test.db")

@pytest.fixture(name="client")
def client_fixture(db_session):
    # Override get_db to use the fixture's session
    def override_get_db():
        try:
            yield db_session
        finally:
            db_session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()

# Example for cleanup if using file-based SQLite for all tests
# This runs once after all tests are collected and run
def pytest_sessionfinish(session, exitstatus):
    if settings.DATABASE_URL == "sqlite:///./test.db" and os.path.exists("./test.db"):
        os.remove("./test.db")
