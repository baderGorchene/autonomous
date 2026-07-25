from fastapi.testclient import TestClient
from src import models
import pytest

def test_language_toggle_default_en(client: TestClient, test_owner: models.Owner):
    response = client.get("/login")
    assert response.status_code == 200
    assert "Login to your account" in response.text 
    assert "English" in response.text 
    assert "العربية" in response.text 
    assert "Français" in response.text 
    assert "locale=en" in response.cookies.get("locale") 

def test_language_toggle_ar_login(client: TestClient):
    response = client.get("/login", cookies={"locale": "ar"})
    assert response.status_code == 200
    assert "تسجيل الدخول إلى حسابك" in response.text 
    assert "locale=ar" in response.cookies.get("locale")

def test_language_toggle_fr_login(client: TestClient):
    response = client.get("/login", cookies={"locale": "fr"})
    assert response.status_code == 200
    assert "Connectez-vous à votre compte" in response.text 
    assert "locale=fr" in response.cookies.get("locale")

def test_language_toggle_en_booking_page(client: TestClient, test_owner: models.Owner):
    response = client.get(f"/{test_owner.slug}", cookies={"locale": "en"})
    assert response.status_code == 200
    assert "Book an Appointment" in response.text
    assert "Your Name" in response.text

def test_language_toggle_ar_booking_page(client: TestClient, test_owner: models.Owner):
    response = client.get(f"/{test_owner.slug}", cookies={"locale": "ar"})
    assert response.status_code == 200
    assert "احجز موعدًا" in response.text
    assert "اسمك" in response.text

def test_language_toggle_fr_booking_page(client: TestClient, test_owner: models.Owner):
    response = client.get(f"/{test_owner.slug}", cookies={"locale": "fr"})
    assert response.status_code == 200
    assert "Réserver un rendez-vous" in response.text
    assert "Votre nom" in response.text

def test_language_toggle_via_endpoint(client: TestClient, test_owner: models.Owner):
    response = client.get("/set_language/ar", follow_redirects=False)
    assert response.status_code == 302
    assert "locale=ar" in response.cookies.get("locale")

    response = client.get("/login") 
    assert "تسجيل الدخول إلى حسابك" in response.text 
    
    response = client.get("/set_language/fr", follow_redirects=False)
    assert response.status_code == 302
    assert "locale=fr" in response.cookies.get("locale")

    response = client.get("/login")
    assert "Connectez-vous à votre compte" in response.text 

def test_language_toggle_via_query_param(client: TestClient, test_owner: models.Owner):
    response = client.get(f"/{test_owner.slug}?lang=ar")
    assert response.status_code == 200
    assert "احجز موعدًا" in response.text
    assert "اسمك" in response.text
    assert "locale=ar" in response.cookies.get("locale") 
