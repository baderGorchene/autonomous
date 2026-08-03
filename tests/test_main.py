import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Assuming `main` is in the parent directory of `tests`
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from main import app, get_db, create_tables
from config import settings
from database import Base

# Override settings for testing
settings.TESTING = True
settings.DATABASE_URL = "sqlite:///./test_sql_app.db"

# Setup test database
engine = create_engine(settings.DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(name="db_session")
def db_session_fixture():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)

@pytest.fixture(name="client")
def client_fixture(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            db_session.close()
    
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()

def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

# Add a simple test for the root path to ensure it loads
def test_root_redirect(client):
    response = client.get("/")
    assert response.status_code == 200 # Should return the booking page or a redirect for owner
    # Depending on the actual implementation of the root path, this might need adjustment
    # For now, a 200 is acceptable if it's meant to serve some content or redirect internally.
    # If it's meant to redirect to /owner/signup or a specific booking page, check for 302/307 and Location header.


# Example for a simple owner signup test (will fail without proper data, just for structure)
def test_owner_signup_page(client):
    response = client.get("/owner/signup")
    assert response.status_code == 200
    assert "Sign Up" in response.text
