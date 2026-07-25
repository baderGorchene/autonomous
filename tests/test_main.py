from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from src import models

def test_health_check(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_root_redirects_to_login(client: TestClient):
    response = client.get("/", allow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/login"

def test_login_page(client: TestClient):
    response = client.get("/login")
    assert response.status_code == 200
    assert "Login to your account" in response.text

def test_signup_page(client: TestClient):
    response = client.get("/signup")
    assert response.status_code == 200
    assert "Create Your Account" in response.text
