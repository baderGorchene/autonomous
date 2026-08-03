import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Import app and database components from src
from src.main import app
from src.database import get_db, Base
from src.config import settings

# Override DATABASE_URL for testing to use an in-memory SQLite database
settings.DATABASE_URL = "sqlite:///:memory:"
settings.TESTING = True

# Setup a test database engine and session for overriding get_db
test_engine = create_engine(settings.DATABASE_URL)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

@pytest.fixture(name="db_session")
def db_session_fixture():
    Base.metadata.create_all(bind=test_engine) # Create tables for tests
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=test_engine) # Drop tables after tests

# Override the get_db dependency to use the test database session
def override_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_root_page():
    response = client.get("/")
    assert response.status_code == 200
    assert "Welcome to BookSlot!" in response.text
