import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.main import app, get_db
from src.database import Base
from src import models, security, crud, schemas
import os
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

# Setup for testing database
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_bookslot.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(name="db_session")
def db_session_fixture():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)

@pytest.fixture(name="client")
def client_fixture(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            db_session.close()
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()

@pytest.fixture
def test_owner(db_session):
    owner_data = schemas.OwnerCreate(
        name="Test Owner",
        email="test@example.com",
        password="testpassword",
        business_name="Test Business",
        slug="test-business"
    )
    owner = crud.create_owner(db_session, owner_data)
    # Add some services and availability for the owner if needed for booking page
    owner.services_json = [{"id": 1, "name": "Consultation", "price": 50, "duration": 30}]
    owner.availability_json = {"monday": [{"start": "09:00", "end": "17:00"}]}
    db_session.add(owner)
    db_session.commit()
    db_session.refresh(owner)
    return owner

@pytest.fixture
def authenticated_client(client, test_owner):
    response = client.post("/auth/token", data={"username": test_owner.email, "password": "testpassword"})
    assert response.status_code == 200
    token = response.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    return client

def test_i18n_dashboard_english(authenticated_client):
    response = authenticated_client.get("/dashboard?lang=en")
    assert response.status_code == 200
    soup = BeautifulSoup(response.content, 'html.parser')
    assert soup.find('h1').text == "Welcome, Test Owner!"
    assert "Upcoming Bookings" in response.text
    assert "Profile" in response.text
    assert "English" in response.text
    assert "Arabic" in response.text
    assert "French" in response.text

def test_i18n_dashboard_arabic(authenticated_client):
    response = authenticated_client.get("/dashboard?lang=ar")
    assert response.status_code == 200
    soup = BeautifulSoup(response.content, 'html.parser')
    assert "أهلاً, Test Owner!" in soup.find('h1').text 
    assert "لوحة القيادة" in response.text
    assert "الحجوزات القادمة" in response.text
    assert "الملف الشخصي" in response.text
    assert "الإنجليزية" in response.text 
    assert "العربية" in response.text
    assert "الفرنسية" in response.text

def test_i18n_dashboard_french(authenticated_client):
    response = authenticated_client.get("/dashboard?lang=fr")
    assert response.status_code == 200
    soup = BeautifulSoup(response.content, 'html.parser')
    assert "Bienvenue, Test Owner!" in soup.find('h1').text
    assert "Tableau de bord" in response.text
    assert "Prochaines réservations" in response.text
    assert "Profil" in response.text
    assert "Anglais" in response.text
    assert "Arabe" in response.text
    assert "Français" in response.text

def test_i18n_booking_page_english(client, test_owner):
    response = client.get(f"/book/{test_owner.slug}/1?lang=en")
    assert response.status_code == 200
    soup = BeautifulSoup(response.content, 'html.parser')
    assert "Book a Slot" in soup.find('title').text
    assert "Book an Appointment with Test Business" in soup.find('h1').text
    assert "Your Name" in response.text
    assert "English" in response.text
    assert "Arabic" in response.text
    assert "French" in response.text

def test_i18n_booking_page_arabic(client, test_owner):
    response = client.get(f"/book/{test_owner.slug}/1?lang=ar")
    assert response.status_code == 200
    soup = BeautifulSoup(response.content, 'html.parser')
    assert "احجز موعدًا" in soup.find('title').text
    assert "احجز موعدًا مع Test Business" in soup.find('h1').text
    assert "اسمك" in response.text
    assert "الإنجليزية" in response.text
    assert "العربية" in response.text
    assert "الفرنسية" in response.text

def test_i18n_booking_page_french(client, test_owner):
    response = client.get(f"/book/{test_owner.slug}/1?lang=fr")
    assert response.status_code == 200
    soup = BeautifulSoup(response.content, 'html.parser')
    assert "Réserver un créneau" in soup.find('title').text
    assert "Prendre rendez-vous avec Test Business" in soup.find('h1').text
    assert "Votre nom" in response.text
    assert "Anglais" in response.text
    assert "Arabe" in response.text
    assert "Français" in response.text

def test_i18n_language_toggle_links(client, test_owner):
    response = client.get(f"/book/{test_owner.slug}/1?lang=en")
    soup = BeautifulSoup(response.content, 'html.parser')
    english_link = soup.find('a', string="English")
    arabic_link = soup.find('a', string="Arabic")
    french_link = soup.find('a', string="French")

    assert english_link['href'] == f"/book/{test_owner.slug}/1?lang=en"
    assert arabic_link['href'] == f"/book/{test_owner.slug}/1?lang=ar"
    assert french_link['href'] == f"/book/{test_owner.slug}/1?lang=fr"

    response_ar = client.get(f"/book/{test_owner.slug}/1?lang=ar")
    soup_ar = BeautifulSoup(response_ar.content, 'html.parser')
    english_link_ar = soup_ar.find('a', string="الإنجليزية")
    arabic_link_ar = soup_ar.find('a', string="العربية")
    french_link_ar = soup_ar.find('a', string="الفرنسية")
    
    assert english_link_ar['href'] == f"/book/{test_owner.slug}/1?lang=en"
    assert arabic_link_ar['href'] == f"/book/{test_owner.slug}/1?lang=ar"
    assert french_link_ar['href'] == f"/book/{test_owner.slug}/1?lang=fr"

    response_fr = client.get(f"/book/{test_owner.slug}/1?lang=fr")
    soup_fr = BeautifulSoup(response_fr.content, 'html.parser')
    english_link_fr = soup_fr.find('a', string="Anglais")
    arabic_link_fr = soup_fr.find('a', string="Arabe")
    french_link_fr = soup_fr.find('a', string="Français")
    
    assert english_link_fr['href'] == f"/book/{test_owner.slug}/1?lang=en"
    assert arabic_link_fr['href'] == f"/book/{test_owner.slug}/1?lang=ar"
    assert french_link_fr['href'] == f"/book/{test_owner.slug}/1?lang=fr"