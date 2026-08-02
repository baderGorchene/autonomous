import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.main import app, get_db
from src.database import Base
from src.config import settings

# Override settings for testing
settings.TESTING = True
settings.DATABASE_URL = "sqlite:///./test.db" # Use a separate test database

# Setup a test database
SQLALCHEMY_DATABASE_URL = settings.DATABASE_URL
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(name="db_session")
def db_session_fixture():
    # Create tables
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine) # Clean up after tests

@pytest.fixture(name="client")
def client_fixture(db_session: TestingSessionLocal):
    def override_get_db():
        try:
            yield db_session
        finally:
            db_session.close()
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()

def test_health_check(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    assert "BookSlot Health Check: OK" in response.text

def test_root_redirect(client: TestClient):
    response = client.get("/")
    assert response.status_code == 302
    assert response.headers["location"] == "/owner/login"

def test_owner_login_page(client: TestClient):
    response = client.get("/owner/login")
    assert response.status_code == 200
    assert "Login" in response.text # Assuming "Login" text is in owner_login.html
