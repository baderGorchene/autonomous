import pytest
from fastapi.testclient import TestClient
from src.main import app
from unittest.mock import patch, MagicMock

client = TestClient(app)

# Mock the get_current_owner dependency for dashboard tests
@pytest.fixture(autouse=True)
def mock_security_dependency():
    with patch('src.security.get_current_owner') as mock_get_current_owner:
        mock_owner = MagicMock()
        mock_owner.id = 1
        mock_owner.name = "Test Owner"
        mock_owner.email = "owner@example.com"
        mock_owner.business_name = "Test Business"
        mock_owner.slug = "test-business"
        mock_owner.phone = "+1234567890"
        mock_owner.services_json = "[{"name": "Service 1", "duration_minutes": 30, "price": 50.0}]"
        mock_owner.availability_json = "{"Monday": [{"day_of_week": "Monday", "start_time": "09:00", "end_time": "17:00"}]}"
        mock_get_current_owner.return_value = mock_owner
        yield

# Mock the get_db dependency for database interactions
@pytest.fixture(autouse=True)
def mock_db_dependency():
    with patch('src.database.SessionLocal') as mock_SessionLocal:
        mock_db_session = MagicMock()
        mock_SessionLocal.return_value = mock_db_session
        
        # Mock for crud.get_owner_by_slug for public booking page
        mock_owner = MagicMock()
        mock_owner.id = 1
        mock_owner.name = "Test Owner"
        mock_owner.email = "owner@example.com"
        mock_owner.business_name = "Test Business"
        mock_owner.slug = "test-business-public"
        mock_owner.phone = "+1234567890"
        mock_owner.services_json = "[{"name": "Public Service", "duration_minutes": 60, "price": 100.0}]"
        mock_owner.availability_json = "{"Tuesday": [{"day_of_week": "Tuesday", "start_time": "10:00", "end_time": "18:00"}]}"
        
        mock_db_session.query.return_value.filter.return_value.first.return_value = mock_owner
        
        yield mock_db_session

def test_dashboard_language_toggle_en():
    response = client.get("/dashboard?lang=en")
    assert response.status_code == 200
    assert "Welcome" in response.text
    assert "Your Profile" in response.text
    assert "Upcoming Bookings" in response.text

def test_dashboard_language_toggle_ar():
    response = client.get("/dashboard?lang=ar")
    assert response.status_code == 200
    assert "أهلاً بك" in response.text
    assert "ملفك الشخصي" in response.text
    assert "الحجوزات القادمة" in response.text
    assert "direction: rtl" in response.text # Check for RTL styling

def test_dashboard_language_toggle_fr():
    response = client.get("/dashboard?lang=fr")
    assert response.status_code == 200
    assert "Bienvenue" in response.text
    assert "Votre Profil" in response.text
    assert "Prochaines Réservations" in response.text

def test_booking_page_language_toggle_en():
    response = client.get("/book/test-business-public?lang=en")
    assert response.status_code == 200
    assert "Book an Appointment" in response.text
    assert "Select a Service" in response.text

def test_booking_page_language_toggle_ar():
    response = client.get("/book/test-business-public?lang=ar")
    assert response.status_code == 200
    assert "احجز موعدًا" in response.text
    assert "اختر خدمة" in response.text
    assert "direction: rtl" in response.text # Check for RTL styling

def test_booking_page_language_toggle_fr():
    response = client.get("/book/test-business-public?lang=fr")
    assert response.status_code == 200
    assert "Réserver un rendez-vous" in response.text
    assert "Sélectionner un service" in response.text

def test_booking_confirmation_page_language_toggle_en():
    response = client.get("/booking-confirmation/test-business-public?lang=en")
    assert response.status_code == 200
    assert "Booking Confirmed!" in response.text
    assert "Thank you for booking with" in response.text

def test_booking_confirmation_page_language_toggle_ar():
    response = client.get("/booking-confirmation/test-business-public?lang=ar")
    assert response.status_code == 200
    assert "تم تأكيد الحجز" in response.text
    assert "شكرا لحجزك مع" in response.text
    assert "direction: rtl" in response.text # Check for RTL styling

def test_booking_confirmation_page_language_toggle_fr():
    response = client.get("/booking-confirmation/test-business-public?lang=fr")
    assert response.status_code == 200
    assert "Réservation Confirmée" in response.text
    assert "Merci d'avoir réservé avec" in response.text
