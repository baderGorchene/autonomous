import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from src.main import app, get_db, PROJECT_ROOT, TEMPLATES_DIR
from src.database import Base
from src.models import Owner
from src.security import get_password_hash
from src.routes import auth
import os
from jinja2 import Environment, FileSystemLoader
from jinja2.ext import i18n
import gettext

# Setup a test database
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(name="session")
def session_fixture():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)

@pytest.fixture(name="client")
def client_fixture(session):
    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()

# Helper to get the Jinja2 environment for a specific locale in tests
def get_test_jinja_env(locale='en'):
    env = Environment(loader=FileSystemLoader(TEMPLATES_DIR), extensions=[i18n])
    localedir = os.path.join(PROJECT_ROOT, 'locales')
    translate = gettext.translation('messages', localedir, languages=[locale], fallback=True)
    env.install_gettext_translations(translate)
    return env

# Mock owner for dashboard tests
@pytest.fixture
def mock_owner(session):
    hashed_password = get_password_hash("testpassword")
    owner = Owner(
        name="Test Owner",
        email="test@example.com",
        hashed_password=hashed_password,
        business_name="Test Business",
        slug="test-business",
        services_json=[],
        availability_json={},
        phone="1234567890"
    )
    session.add(owner)
    session.commit()
    session.refresh(owner)
    return owner

@pytest.fixture
def mock_current_owner(mock_owner):
    def _override_get_current_owner():
        return mock_owner
    app.dependency_overrides[auth.get_current_owner] = _override_get_current_owner
    yield
    app.dependency_overrides.clear()

def test_i18n_dashboard_english(client, mock_current_owner):
    response = client.get("/dashboard?lang=en")
    assert response.status_code == 200
    content = response.text
    assert "Dashboard" in content
    assert "Upcoming Bookings" in content
    assert "Profile Settings" in content
    assert "Language" in content
    assert "Logout" in content

def test_i18n_dashboard_arabic(client, mock_current_owner):
    response = client.get("/dashboard?lang=ar")
    assert response.status_code == 200
    content = response.text
    assert "لوحة التحكم" in content
    assert "الحجوزات القادمة" in content
    assert "إعدادات الملف الشخصي" in content
    assert "اللغة" in content
    assert "تسجيل الخروج" in content

def test_i18n_dashboard_french(client, mock_current_owner):
    response = client.get("/dashboard?lang=fr")
    assert response.status_code == 200
    content = response.text
    assert "Tableau de bord" in content
    assert "Prochaines Réservations" in content
    assert "Paramètres du profil" in content
    assert "Langue" in content
    assert "Déconnexion" in content

def test_i18n_booking_page_english(client, session, mock_owner):
    response = client.get(f"/book/{mock_owner.slug}?lang=en")
    assert response.status_code == 200
    content = response.text
    assert f"Book an appointment with {mock_owner.business_name}" in content
    assert "Service" in content
    assert "Date" in content
    assert "Time" in content
    assert "Your Name" in content
    assert "Your Email" in content
    assert "Your Phone (WhatsApp)" in content
    assert "Book Now" in content

def test_i18n_booking_page_arabic(client, session, mock_owner):
    response = client.get(f"/book/{mock_owner.slug}?lang=ar")
    assert response.status_code == 200
    content = response.text
    assert f"احجز موعدًا مع {mock_owner.business_name}" in content
    assert "الخدمة" in content
    assert "التاريخ" in content
    assert "الوقت" in content
    assert "اسمك" in content
    assert "بريدك الإلكتروني" in content
    assert "رقم هاتفك (واتساب)" in content
    assert "احجز الآن" in content

def test_i18n_booking_page_french(client, session, mock_owner):
    response = client.get(f"/book/{mock_owner.slug}?lang=fr")
    assert response.status_code == 200
    content = response.text
    assert f"Réservez un rendez-vous avec {mock_owner.business_name}" in content
    assert "Service" in content
    assert "Date" in content
    assert "Heure" in content
    assert "Votre Nom" in content
    assert "Votre E-mail" in content
    assert "Votre Téléphone (WhatsApp)" in content
    assert "Réserver maintenant" in content

def test_dashboard_language_toggle(client, mock_current_owner):
    response = client.get("/dashboard?lang=en")
    assert response.status_code == 200
    assert 'href="/dashboard?lang=ar"' in response.text
    assert 'href="/dashboard?lang=fr"' in response.text
    assert 'href="/dashboard?lang=en"' in response.text

    response = client.get("/dashboard?lang=ar")
    assert response.status_code == 200
    assert 'href="/dashboard?lang=ar"' in response.text
    assert 'href="/dashboard?lang=fr"' in response.text
    assert 'href="/dashboard?lang=en"' in response.text

    response = client.get("/dashboard?lang=fr")
    assert response.status_code == 200
    assert 'href="/dashboard?lang=ar"' in response.text
    assert 'href="/dashboard?lang=fr"' in response.text
    assert 'href="/dashboard?lang=en"' in response.text

def test_booking_page_language_toggle(client, session, mock_owner):
    response = client.get(f"/book/{mock_owner.slug}?lang=en")
    assert response.status_code == 200
    assert f'href="/book/{mock_owner.slug}?lang=ar"' in response.text
    assert f'href="/book/{mock_owner.slug}?lang=fr"' in response.text
    assert f'href="/book/{mock_owner.slug}?lang=en"' in response.text

    response = client.get(f"/book/{mock_owner.slug}?lang=ar")
    assert response.status_code == 200
    assert f'href="/book/{mock_owner.slug}?lang=ar"' in response.text
    assert f'href="/book/{mock_owner.slug}?lang=fr"' in response.text
    assert f'href="/book/{mock_owner.slug}?lang=en"' in response.text

    response = client.get(f"/book/{mock_owner.slug}?lang=fr")
    assert response.status_code == 200
    assert f'href="/book/{mock_owner.slug}?lang=ar"' in response.text
    assert f'href="/book/{mock_owner.slug}?lang=fr"' in response.text
    assert f'href="/book/{mock_owner.slug}?lang=en"' in response.text