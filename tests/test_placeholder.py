from fastapi.testclient import TestClient
import pytest
from src.main import app # Import the app instance

# Assuming conftest.py sets up the client fixture with the overridden database
# and creates tables.

def test_health_check(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_create_owner_and_login(client: TestClient):
    # Test signup
    owner_data = {
        "name": "Test Owner",
        "email": "test@example.com",
        "password": "testpassword",
        "business_name": "Test Business",
        "slug": "test-business",
        "phone": "+1234567890"
    }
    response = client.post("/signup", json=owner_data)
    assert response.status_code == 200, response.json()
    new_owner = response.json()
    assert new_owner["email"] == "test@example.com"
    assert new_owner["business_name"] == "Test Business"

    # Test login
    login_data = {
        "username": "test@example.com",
        "password": "testpassword"
    }
    response = client.post("/token", data=login_data)
    assert response.status_code == 200, response.json()
    token_data = response.json()
    assert "access_token" in token_data
    assert token_data["token_type"] == "bearer"

    # Test fetching owner profile with token
    headers = {"Authorization": f"Bearer {token_data['access_token']}"}
    response = client.get("/owner/me", headers=headers)
    assert response.status_code == 200, response.json()
    owner_profile = response.json()
    assert owner_profile["email"] == "test@example.com"
    assert owner_profile["name"] == "Test Owner"
