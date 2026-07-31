from fastapi.testclient import TestClient
import pytest

def test_health_check(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_signup_page(client: TestClient):
    response = client.get("/signup")
    assert response.status_code == 200
    assert "<h1>Sign Up</h1>" in response.text
    assert "Your Name" in response.text

def test_successful_signup(client: TestClient):
    response = client.post(
        "/signup",
        data={
            "name": "Test Owner",
            "email": "test@example.com",
            "password": "testpassword",
            "business_name": "Test Business",
            "slug": "test-business",
            "phone": "+1234567890"
        }
    )
    assert response.status_code == 200
    assert "Account created successfully! Please log in." in response.text

def test_signup_duplicate_email(client: TestClient):
    client.post(
        "/signup",
        data={
            "name": "Test Owner",
            "email": "duplicate@example.com",
            "password": "testpassword",
            "business_name": "Test Business",
            "slug": "unique-slug-1",
            "phone": "+1234567890"
        }
    )
    response = client.post(
        "/signup",
        data={
            "name": "Another Owner",
            "email": "duplicate@example.com",
            "password": "anotherpassword",
            "business_name": "Another Business",
            "slug": "unique-slug-2",
            "phone": "+1234567891"
        }
    )
    assert response.status_code == 400
    assert "Email already registered" in response.text

def test_signup_duplicate_slug(client: TestClient):
    client.post(
        "/signup",
        data={
            "name": "Test Owner",
            "email": "slugtest@example.com",
            "password": "testpassword",
            "business_name": "Test Business",
            "slug": "duplicate-slug",
            "phone": "+1234567890"
        }
    )
    response = client.post(
        "/signup",
        data={
            "name": "Another Owner",
            "email": "anotherslugtest@example.com",
            "password": "anotherpassword",
            "business_name": "Another Business",
            "slug": "duplicate-slug",
            "phone": "+1234567891"
        }
    )
    assert response.status_code == 400
    assert "Business slug already taken" in response.text

def test_login_page(client: TestClient):
    response = client.get("/login")
    assert response.status_code == 200
    assert "<h1>Login</h1>" in response.text
    assert "Email" in response.text

def test_successful_login(client: TestClient):
    client.post(
        "/signup",
        data={
            "name": "Login Owner",
            "email": "login@example.com",
            "password": "loginpassword",
            "business_name": "Login Business",
            "slug": "login-business",
            "phone": "+1234567890"
        }
    )
    response = client.post(
        "/login",
        data={"email": "login@example.com", "password": "loginpassword"},
        follow_redirects=False
    )
    assert response.status_code == 303
    assert response.headers["Location"] == "/dashboard"
    assert "access_token" in response.cookies
    assert response.cookies["access_token"].startswith("Bearer ")

def test_login_invalid_credentials(client: TestClient):
    response = client.post(
        "/login",
        data={"email": "nonexistent@example.com", "password": "wrongpassword"}
    )
    assert response.status_code == 400
    assert "Incorrect email or password" in response.text

def test_login_wrong_password(client: TestClient):
    client.post(
        "/signup",
        data={
            "name": "Wrong Pass Owner",
            "email": "wrongpass@example.com",
            "password": "correctpassword",
            "business_name": "Wrong Pass Business",
            "slug": "wrongpass-business",
            "phone": "+1234567890"
        }
    )
    response = client.post(
        "/login",
        data={"email": "wrongpass@example.com", "password": "incorrectpassword"}
    )
    assert response.status_code == 400
    assert "Incorrect email or password" in response.text
