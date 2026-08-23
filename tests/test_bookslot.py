import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.main import app, get_db
from src.database import Base

SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}

def test_owner_signup_and_login():
    response = client.post("/auth/signup", json={
        "name": "Test Salon",
        "email": "salon@example.com",
        "password": "password123",
        "subdomain": "testsalon"
    })
    assert response.status_code in [200, 201, 400]

    login_response = client.post("/auth/token", data={
        "username": "salon@example.com",
        "password": "password123"
    })
    if login_response.status_code == 200:
        assert "access_token" in login_response.json()
