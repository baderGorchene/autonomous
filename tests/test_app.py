import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.database import Base, get_db
from src.main import app

SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
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
    response = client.post("/api/auth/signup", json={
        "email": "testowner@example.com",
        "password": "secretpassword",
        "name": "Test Owner",
        "business_name": "Test Salon",
        "slug": "test-salon"
    })
    assert response.status_code in [200, 201]
    
    response = client.post("/api/auth/token", data={
        "username": "testowner@example.com",
        "password": "secretpassword"
    })
    assert response.status_code == 200
    assert "access_token" in response.json()
