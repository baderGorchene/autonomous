import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy_utils import database_exists, create_database, drop_database
import os

from src.main import app, get_db
from src.database import Base
from src import models, security, crud, schemas
import json

# Use a separate test database
TEST_DATABASE_URL_I18N = "sqlite:///./test_i18n.db"

@pytest.fixture(scope="session")
def test_engine_i18n():
    if "sqlite" in TEST_DATABASE_URL_I18N and os.path.exists("./test_i18n.db"):
        os.remove("./test_i18n.db")
    
    test_engine = create_engine(TEST_DATABASE_URL_I18N, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=test_engine)
    yield test_engine
    Base.metadata.drop_all(bind=test_engine)
    if "sqlite" in TEST_DATABASE_URL_I18N and os.path.exists("./test_i18n.db"):
        os.remove("./test_i18n.db")

@pytest.fixture(scope="function")
def db_session_i18n(test_engine_i18n):
    connection = test_engine_i18n.connect()
    transaction = connection.begin()
    SessionTesting = sessionmaker(autocommit=False, autoflush=False, bind=connection)
    session = SessionTesting()
    yield session
    session.close()
    transaction.rollback()
    connection.close()

@pytest.fixture(scope="function")
def client_i18n(db_session_i18n):
    def override_get_db():
        try:
            yield db_session_i18n
        finally:
            db_session_i18n.close()
    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()

@pytest.fixture
def test_owner_data_i18n():
    return {
        "name": "I18n Test Owner",
        "email": "i18n_test@example.com",
        "password": "i18npassword",
        "business_name": "I18n Business",
        "slug": "i18n-business",
        "phone": "+15551234567"
    }

@pytest.fixture
def auth_owner_i18n(client_i18n, db_session_i18n, test_owner_data_i18n):
    # Create owner
    owner_create = schemas.OwnerCreate(**test_owner_data_i18n)
    owner = crud.create_owner(db_session_i18n, owner_create)
    
    # Login and get token
    response = client_i18n.post(
        "/login",
        data={"email": test_owner_data_i18n["email"], "password": test_owner_data_i18n["password"]}
    )
    assert response.status_code == 302
    access_token = response.cookies.get("access_token")
    assert access_token is not None
    return owner, access_token

# --- I18n Test Cases ---

def test_language_toggle_on_login_page(client_i18n):
    # Default English
    response = client_i18n.get("/login")
    assert response.status_code == 200
    assert "Login" in response.text
    assert "Email" in response.text

    # Switch to Arabic
    response = client_i18n.get("/set-locale/ar", headers={"referer": "/login"})
    assert response.status_code == 302
    assert response.headers["location"] == "/login"
    assert response.cookies.get("locale") == "ar"

    response = client_i18n.get("/login", cookies={"locale": "ar"})
    assert response.status_code == 200
    assert "تسجيل الدخول" in response.text
    assert "البريد الإلكتروني" in response.text

    # Switch to French
    response = client_i18n.get("/set-locale/fr", headers={"referer": "/login"})
    assert response.status_code == 302
    assert response.headers["location"] == "/login"
    assert response.cookies.get("locale") == "fr"

    response = client_i18n.get("/login", cookies={"locale": "fr"})
    assert response.status_code == 200
    assert "Connexion" in response.text
    assert "E-mail" in response.text

def test_language_on_dashboard(client_i18n, auth_owner_i18n):
    owner, access_token = auth_owner_i18n
    
    # English Dashboard
    response = client_i18n.get("/dashboard", cookies={"access_token": access_token, "locale": "en"})
    assert response.status_code == 200
    assert "Welcome" in response.text
    assert "Upcoming Bookings" in response.text
    assert owner.name in response.text

    # Arabic Dashboard
    response = client_i18n.get("/dashboard", cookies={"access_token": access_token, "locale": "ar"})
    assert response.status_code == 200
    assert "أهلاً" in response.text
    assert "الحجوزات القادمة" in response.text
    assert owner.name in response.text

    # French Dashboard
    response = client_i18n.get("/dashboard", cookies={"access_token": access_token, "locale": "fr"})
    assert response.status_code == 200
    assert "Bienvenue" in response.text
    assert "Prochaines réservations" in response.text
    assert owner.name in response.text

def test_language_on_booking_page(client_i18n, db_session_i18n, auth_owner_i18n):
    owner, _ = auth_owner_i18n
    
    # Update owner with services and availability for the booking page to display them
    owner.services_json = json.dumps([{"name": "Service Test", "duration": 30, "price": 25.0}])
    owner.availability_json = json.dumps([{"day_of_week": 0, "start_time": "09:00", "end_time": "17:00"}])
    db_session_i18n.add(owner)
    db_session_i18n.commit()
    db_session_i18n.refresh(owner)

    # English Booking Page
    response = client_i18n.get(f"/book/{owner.slug}", cookies={"locale": "en"})
    assert response.status_code == 200
    assert "Book an Appointment with" in response.text
    assert "Select a Service" in response.text
    assert "Monday" in response.text # from date_obj.day_name

    # Arabic Booking Page
    response = client_i18n.get(f"/book/{owner.slug}", cookies={"locale": "ar"})
    assert response.status_code == 200
    assert "احجز موعداً مع" in response.text
    assert "اختر خدمة" in response.text
    assert "الاثنين" in response.text # from date_obj.day_name

    # French Booking Page
    response = client_i18n.get(f"/book/{owner.slug}", cookies={"locale": "fr"})
    assert response.status_code == 200
    assert "Prendre rendez-vous avec" in response.text
    assert "Sélectionnez un service" in response.text
    assert "Lundi" in response.text # from date_obj.day_name
