from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

def test_health_check(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}

def test_owner_signup_and_login(client: TestClient):
    signup_response = client.post("/api/auth/signup", json={
        "email": "owner@example.com",
        "password": "securepassword123",
        "name": "John Doe",
        "business_name": "John's Salon",
        "slug": "johns-salon"
    })
    assert signup_response.status_code == 200
    data = signup_response.json()
    assert data["email"] == "owner@example.com"
    assert data["slug"] == "johns-salon"

    # Test Login
    login_response = client.post("/api/auth/login", data={
        "username": "owner@example.com",
        "password": "securepassword123"
    })
    assert login_response.status_code == 200
    token_data = login_response.json()
    assert "access_token" in token_data
    assert token_data["token_type"] == "bearer"
