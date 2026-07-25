from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from src import models, security, crud
import pytest

def test_create_owner_signup(client: TestClient, db: Session):
    response = client.post(
        "/owner/signup",
        data={
            "name": "New User",
            "email": "newuser@example.com",
            "password": "strongpassword",
            "business_name": "New Business",
            "slug": "new-business-slug"
        },
        follow_redirects=False
    )
    assert response.status_code == 302
    assert response.headers["location"] == "/login"

    owner = crud.get_owner_by_email(db, "newuser@example.com")
    assert owner is not None
    assert owner.name == "New User"
    assert security.verify_password("strongpassword", owner.hashed_password)

def test_create_owner_signup_invalid_email(client: TestClient):
    response = client.post(
        "/owner/signup",
        data={
            "name": "Invalid Email",
            "email": "invalid-email",
            "password": "strongpassword",
            "business_name": "Invalid Email Business",
            "slug": "invalid-email-slug"
        }
    )
    assert response.status_code == 400
    assert "Invalid email address." in response.text

def test_create_owner_signup_duplicate_email(client: TestClient, test_owner: models.Owner):
    response = client.post(
        "/owner/signup",
        data={
            "name": "Duplicate User",
            "email": test_owner.email,
            "password": "strongpassword",
            "business_name": "Duplicate Business",
            "slug": "another-slug"
        }
    )
    assert response.status_code == 400
    assert "This email is already registered." in response.text

def test_create_owner_signup_duplicate_slug(client: TestClient, test_owner: models.Owner):
    response = client.post(
        "/owner/signup",
        data={
            "name": "Duplicate Slug User",
            "email": "duplicate.slug@example.com",
            "password": "strongpassword",
            "business_name": "Duplicate Slug Business",
            "slug": test_owner.slug
        }
    )
    assert response.status_code == 400
    assert "This slug is already taken." in response.text

def test_login_success(client: TestClient, test_owner: models.Owner):
    response = client.post(
        "/token",
        data={"username": test_owner.email, "password": "testpassword"},
        follow_redirects=False
    )
    assert response.status_code == 302
    assert response.headers["location"] == "/owner/dashboard"
    assert "access_token" in response.cookies
    assert "token_type" in response.cookies

def test_login_invalid_credentials(client: TestClient):
    response = client.post(
        "/token",
        data={"username": "nonexistent@example.com", "password": "wrongpassword"}
    )
    assert response.status_code == 401
    assert "Incorrect email or password" in response.text

def test_logout(authenticated_client: TestClient):
    response = authenticated_client.get("/logout", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/login"
    assert "access_token" not in response.cookies
