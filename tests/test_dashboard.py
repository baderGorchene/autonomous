from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from src import models, schemas, crud
import pytest

def test_owner_dashboard_access_unauthenticated(client: TestClient):
    response = client.get("/owner/dashboard", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"].startswith("/login")

def test_owner_dashboard_access_authenticated(authenticated_client: TestClient, test_owner: models.Owner):
    response = authenticated_client.get("/owner/dashboard")
    assert response.status_code == 200
    assert f"Welcome, {test_owner.name}!" in response.text
    assert f"bookslot.app/{test_owner.slug}" in response.text

def test_update_owner_profile_success(authenticated_client: TestClient, db: Session, test_owner: models.Owner):
    new_name = "Updated Test Owner"
    new_business_name = "Updated Business Name Inc."
    new_phone = "+19876543210"

    response = authenticated_client.post(
        "/owner/profile",
        data={
            "name": new_name,
            "business_name": new_business_name,
            "phone": new_phone
        },
        follow_redirects=False
    )
    assert response.status_code == 302
    assert response.headers["location"] == "/owner/dashboard"

    db.refresh(test_owner)
    assert test_owner.name == new_name
    assert test_owner.business_name == new_business_name
    assert test_owner.phone == new_phone

def test_update_owner_profile_validation_error(authenticated_client: TestClient, test_owner: models.Owner):
    response = authenticated_client.post(
        "/owner/profile",
        data={
            "name": "", 
            "business_name": "Valid Business Name",
            "phone": "invalid-phone" 
        }
    )
    assert response.status_code == 400
    assert "Name is required." in response.text
    assert "Invalid phone number format." in response.text
    assert "Welcome, Test Owner!" in response.text 
