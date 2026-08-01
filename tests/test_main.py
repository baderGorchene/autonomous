from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.main import app, get_db
from src.database import Base
from src.config import settings

# Override DATABASE_URL for testing to use an in-memory SQLite database
settings.TESTING = True
settings.DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(settings.DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create tables for the in-memory database
Base.metadata.create_all(bind=engine)

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)

def test_read_main():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

# Add a basic signup test
def test_signup_owner():
    response = client.post(
        "/owner/signup",
        json={
            "name": "Test Owner",
            "email": "test@example.com",
            "password": "testpassword",
            "business_name": "Test Business",
            "slug": "testbusiness",
            "phone": "+1234567890"
        }
    )
    assert response.status_code == 200
    assert "access_token" in response.json()
    assert response.json()["token_type"] == "bearer"

# Add a basic login test
def test_login_owner():
    # First signup an owner
    client.post(
        "/owner/signup",
        json={
            "name": "Login Test Owner",
            "email": "login@example.com",
            "password": "loginpassword",
            "business_name": "Login Business",
            "slug": "loginbusiness",
            "phone": "+1987654321"
        }
    )
    # Then try to log in
    response = client.post(
        "/owner/token",
        data={"username": "login@example.com", "password": "loginpassword"}
    )
    assert response.status_code == 200
    assert "access_token" in response.json()
    assert response.json()["token_type"] == "bearer"
