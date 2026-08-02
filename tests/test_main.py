import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.main import app, get_db, Base, get_jinja_environment
from src.config import settings
import os
from unittest.mock import patch
import json
from jinja2 import Environment, FileSystemLoader
from jinja2.ext import i18n
import gettext
import datetime

# --- Setup for Testing ---
# 1. Override database for tests
TEST_DATABASE_URL = "sqlite:///:memory:"
test_engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)

@pytest.fixture(scope="function")
def db_session():
    connection = test_engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)
    yield session
    session.close()
    transaction.rollback()
    connection.close()

def override_get_db_test():
    try:
        connection = test_engine.connect()
        transaction = connection.begin()
        session = TestingSessionLocal(bind=connection)
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()

app.dependency_overrides[get_db] = override_get_db_test

# 2. Mock Jinja2 environment for tests (or ensure it loads correctly)
# For i18n tests, we need a real Jinja env. For others, a mock might be simpler.
# Let's use a real one, but ensure paths are correct for tests.
@pytest.fixture(scope="function")
def test_jinja_env(tmp_path):
    # Create dummy templates and locales for testing
    templates_dir = tmp_path / "templates"
    templates_dir.mkdir()
    (templates_dir / "signup.html").write_text("<h1>Signup</h1>{{ error_message }}")
    (templates_dir / "login.html").write_text("<h1>Login</h1>{{ error_message }}")
    (templates_dir / "dashboard.html").write_text("<h1>Dashboard</h1><h2>{{ _('Upcoming Bookings') }}</h2>")
    (templates_dir / "booking_page.html").write_text("<h1>{{ owner.business_name }}</h1><h2>{{ _('Book a Service') }}</h2>")
    (templates_dir / "booking_confirmation.html").write_text("<h1>{{ _('Booking Confirmed!') }}</h1>")
    (templates_dir / "profile.html").write_text("<h1>Profile</h1>")
    (templates_dir / "email").mkdir()
    (templates_dir / "email/customer_confirmation.html").write_text("Customer email content: {{ booking.customer_name }}")
    (templates_dir / "email/owner_notification.html").write_text("Owner email content: {{ booking.owner_name }}")


    locales_dir = tmp_path / "locales"
    locales_dir.mkdir()
    (locales_dir / "ar").mkdir()
    (locales_dir / "ar/LC_MESSAGES").mkdir()
    (locales_dir / "ar/LC_MESSAGES/messages.po").write_text("""
msgid ""
msgstr ""
"Content-Type: text/plain; charset=utf-8\n"
"Content-Transfer-Encoding: 8bit\n"
"Project-Id-Version: BookSlot\n"
"Language-Team: \n"
"Language: ar\n"
"MIME-Version: 1.0\n"

msgid "Upcoming Bookings"
msgstr "الحجوزات القادمة"

msgid "Book a Service"
msgstr "احجز خدمة"

msgid "Booking Confirmed!"
msgstr "تم تأكيد الحجز!"
""")
    (locales_dir / "fr").mkdir()
    (locales_dir / "fr/LC_MESSAGES").mkdir()
    (locales_dir / "fr/LC_MESSAGES/messages.po").write_text("""
msgid ""
msgstr ""
"Content-Type: text/plain; charset=utf-8\n"
"Content-Transfer-Encoding: 8bit\n"
"Project-Id-Version: BookSlot\n"
"Language-Team: \n"
"Language: fr\n"
"MIME-Version: 1.0\n"

msgid "Upcoming Bookings"
msgstr "Prochaines Réservations"

msgid "Book a Service"
msgstr "Réserver un Service"

msgid "Booking Confirmed!"
msgstr "Réservation Confirmée !"
""")

    # Compile .po to .mo
    import subprocess
    subprocess.run(["msgfmt", "-o", str(locales_dir / "ar/LC_MESSAGES/messages.mo"), str(locales_dir / "ar/LC_MESSAGES/messages.po")], check=True)
    subprocess.run(["msgfmt", "-o", str(locales_dir / "fr/LC_MESSAGES/messages.mo"), str(locales_dir / "fr/LC_MESSAGES/messages.po")], check=True)


    original_templates_dir = settings.TEMPLATES_DIR
    original_locales_dir = settings.LOCALES_DIR
    settings.TEMPLATES_DIR = str(templates_dir)
    settings.LOCALES_DIR = str(locales_dir)

    env = Environment(loader=FileSystemLoader(str(templates_dir)), extensions=[i18n])
    # Mock request for get_jinja_environment
    class MockRequest:
        def __init__(self, locale='en'):
            self.session = {'locale': locale}
            self.url_for_called_with = None

        def url_for(self, name, **path_params):
            # Simple mock for url_for
            self.url_for_called_with = (name, path_params)
            if name == "public_booking_page":
                return f"/{path_params.get('owner_slug')}"
            return "/" # Default mock

    class MockRequestFixture:
        def __init__(self, locale='en'):
            self.request = MockRequest(locale)
        def __call__(self):
            return self.request

    # Patch the dependency in main.py
    with patch('src.main.get_jinja_environment', new=lambda request=None: get_jinja_env(request.session.get('locale', 'en')) if request else get_jinja_env('en')):
        yield env
    
    settings.TEMPLATES_DIR = original_templates_dir
    settings.LOCALES_DIR = original_locales_dir

@pytest.fixture(scope="function")
def client(test_jinja_env): # Ensure test_jinja_env is loaded
    with TestClient(app) as c:
        yield c

# 3. Mock notifications to prevent actual external calls during tests
@pytest.fixture(autouse=True)
def mock_notifications():
    with patch("src.notifications.send_email_notification", return_value=True) as mock_send_email, \
         patch("src.notifications.send_whatsapp_notification", return_value=True) as mock_send_whatsapp:
        yield mock_send_email, mock_send_whatsapp

# --- Test Cases ---

def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.text == "<h1>OK</h1>"

def test_signup_and_login(client, db_session):
    # Signup
    signup_data = {
        "name": "Test Owner",
        "email": "test@example.com",
        "password": "password123",
        "business_name": "Test Business",
        "slug": "test-business",
        "phone": "+1234567890"
    }
    response = client.post("/signup", data=signup_data, follow_redirects=False)
    assert response.status_code == 303 # Redirect to login
    assert response.headers['location'] == "/login"

    # Login
    login_data = {
        "username": "test@example.com",
        "password": "password123"
    }
    response = client.post("/login", data=login_data, follow_redirects=False)
    assert response.status_code == 303 # Redirect to dashboard
    assert response.headers['location'] == "/dashboard"
    assert "access_token" in response.cookies

    # Access dashboard with cookie
    response = client.get("/dashboard", cookies={"access_token": response.cookies["access_token"]})
    assert response.status_code == 200
    assert "Dashboard" in response.text
    assert "Test Owner" in response.text

def test_duplicate_email_signup(client, db_session):
    # First signup
    signup_data_1 = {
        "name": "Owner One", "email": "owner1@example.com", "password": "pass",
        "business_name": "Business One", "slug": "business-one", "phone": "+111"
    }
    client.post("/signup", data=signup_data_1)

    # Second signup with same email
    signup_data_2 = {
        "name": "Owner Two", "email": "owner1@example.com", "password": "pass",
        "business_name": "Business Two", "slug": "business-two", "phone": "+222"
    }
    response = client.post("/signup", data=signup_data_2)
    assert response.status_code == 200 # Stays on signup page
    assert "Email already registered." in response.text

def test_duplicate_slug_signup(client, db_session):
    # First signup
    signup_data_1 = {
        "name": "Owner Three", "email": "owner3@example.com", "password": "pass",
        "business_name": "Business Three", "slug": "business-slug", "phone": "+333"
    }
    client.post("/signup", data=signup_data_1)

    # Second signup with same slug
    signup_data_2 = {
        "name": "Owner Four", "email": "owner4@example.com", "password": "pass",
        "business_name": "Business Four", "slug": "business-slug", "phone": "+444"
    }
    response = client.post("/signup", data=signup_data_2)
    assert response.status_code == 200 # Stays on signup page
    assert "Business URL slug already taken." in response.text

def test_unauthenticated_dashboard_access(client):
    response = client.get("/dashboard")
    assert response.status_code == 401 # Unauthorized

def test_profile_update(client, db_session):
    # Signup and login to get a token
    signup_data = {
        "name": "Profile Owner", "email": "profile@example.com", "password": "password",
        "business_name": "Profile Business", "slug": "profile-biz", "phone": "+1122334455"
    }
    client.post("/signup", data=signup_data)
    login_data = {"username": "profile@example.com", "password": "password"}
    login_response = client.post("/login", data=login_data, follow_redirects=False)
    access_token = login_response.cookies["access_token"]

    # Update profile
    updated_services = [{"name": "Haircut", "duration": 30}, {"name": "Shave", "duration": 15}]
    updated_availability = {"monday": [{"start": "09:00", "end": "17:00"}], "tuesday": [{"start": "10:00", "end": "18:00"}]}

    update_data = {
        "name": "Updated Profile Owner",
        "business_name": "Updated Business Name",
        "phone": "+9988776655",
        "services_json": json.dumps(updated_services),
        "availability_json": json.dumps(updated_availability),
    }
    response = client.post("/profile", data=update_data, cookies={"access_token": access_token})
    assert response.status_code == 200
    assert "Profile updated successfully!" in response.text
    assert "Updated Profile Owner" in response.text
    assert "Updated Business Name" in response.text
    assert "Haircut" in response.text # Check if services are rendered
    assert "09:00" in response.text # Check if availability is rendered

    # Verify updates in DB
    owner = db_session.query(models.Owner).filter(models.Owner.email == "profile@example.com").first()
    assert owner.name == "Updated Profile Owner"
    assert owner.business_name == "Updated Business Name"
    assert owner.phone == "+9988776655"
    assert json.loads(owner.services_json) == updated_services
    assert json.loads(owner.availability_json) == updated_availability

def test_public_booking_page_display(client, db_session):
    owner_data = {
        "name": "BookSlot Owner", "email": "bookslot@example.com", "password": "password",
        "business_name": "BookSlot Salon", "slug": "bookslot-salon", "phone": "+12345"
    }
    client.post("/signup", data=owner_data)

    owner = db_session.query(models.Owner).filter(models.Owner.slug == "bookslot-salon").first()
    owner.services_json = json.dumps([{"name": "Cut", "duration": 60}])
    owner.availability_json = json.dumps({"monday": [{"start": "09:00", "end": "17:00"}]})
    db_session.add(owner)
    db_session.commit()

    response = client.get("/bookslot-salon")
    assert response.status_code == 200
    assert "BookSlot Salon" in response.text
    assert "Cut" in response.text
    assert "09:00" in response.text

def test_booking_submission(client, db_session, mock_notifications):
    owner_data = {
        "name": "Booker Owner", "email": "booker@example.com", "password": "password",
        "business_name": "Booker Clinic", "slug": "booker-clinic", "phone": "+15551234567"
    }
    client.post("/signup", data=owner_data)

    owner = db_session.query(models.Owner).filter(models.Owner.slug == "booker-clinic").first()
    owner.services_json = json.dumps([{"name": "Consultation", "duration": 30}])
    # Set availability for today
    today_day = datetime.date.today().strftime('%A').lower()
    owner.availability_json = json.dumps({today_day: [{"start": "09:00", "end": "17:00"}]})
    db_session.add(owner)
    db_session.commit()

    booking_date = datetime.date.today().strftime("%Y-%m-%d")
    booking_time = "10:00"

    booking_data = {
        "customer_name": "Jane Doe",
        "customer_email": "jane@example.com",
        "customer_phone": "+1234567890",
        "service_name": "Consultation",
        "booking_date_str": booking_date,
        "booking_time": booking_time
    }
    response = client.post("/booker-clinic/book", data=booking_data, follow_redirects=False)
    assert response.status_code == 303 # Redirect to confirmation
    assert response.headers['location'] == "/booker-clinic/confirmed"

    # Verify booking in DB
    bookings = db_session.query(models.Booking).filter(models.Booking.owner_id == owner.id).all()
    assert len(bookings) == 1
    assert bookings[0].customer_name == "Jane Doe"
    assert bookings[0].service_name == "Consultation"
    assert bookings[0].booking_date == datetime.date.today()
    assert bookings[0].booking_time == "10:00"

    # Verify notifications were called
    mock_notifications[0].assert_called_once() # Email
    mock_notifications[1].assert_called_once() # WhatsApp

def test_booking_invalid_time(client, db_session):
    owner_data = {
        "name": "Time Owner", "email": "time@example.com", "password": "password",
        "business_name": "Time Clinic", "slug": "time-clinic", "phone": "+15551234567"
    }
    client.post("/signup", data=owner_data)

    owner = db_session.query(models.Owner).filter(models.Owner.slug == "time-clinic").first()
    owner.services_json = json.dumps([{"name": "Consultation", "duration": 30}])
    # Set availability only for 10:00-11:00
    today_day = datetime.date.today().strftime('%A').lower()
    owner.availability_json = json.dumps({today_day: [{"start": "10:00", "end": "11:00"}]})
    db_session.add(owner)
    db_session.commit()

    booking_date = datetime.date.today().strftime("%Y-%m-%d")
    booking_time = "09:00" # Outside available slot

    booking_data = {
        "customer_name": "John Doe",
        "customer_email": "john@example.com",
        "customer_phone": "+1234567890",
        "service_name": "Consultation",
        "booking_date_str": booking_date,
        "booking_time": booking_time
    }
    response = client.post("/time-clinic/book", data=booking_data)
    assert response.status_code == 200 # Renders booking page with error
    assert "The selected time is not available or conflicts with existing bookings." in response.text

def test_i18n_language_toggle_and_content(client, db_session):
    owner_data = {
        "name": "i18n Owner", "email": "i18n@example.com", "password": "password",
        "business_name": "i18n Business", "slug": "i18n-biz", "phone": "+123"
    }
    client.post("/signup", data=owner_data)
    login_data = {"username": "i18n@example.com", "password": "password"}
    login_response = client.post("/login", data=login_data, follow_redirects=False)
    access_token = login_response.cookies["access_token"]

    # Check dashboard in English (default)
    response = client.get("/dashboard", cookies={"access_token": access_token})
    assert response.status_code == 200
    assert "Upcoming Bookings" in response.text

    # Change language to Arabic
    response = client.get("/set_language/ar?redirect_to=/dashboard", cookies={"access_token": access_token}, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers['location'] == "/dashboard"
    
    response = client.get("/dashboard", cookies={"access_token": access_token})
    assert response.status_code == 200
    assert "الحجوزات القادمة" in response.text # Arabic translation

    # Check public booking page in Arabic
    owner = db_session.query(models.Owner).filter(models.Owner.slug == "i18n-biz").first()
    owner.services_json = json.dumps([{"name": "Service AR", "duration": 30}])
    owner.availability_json = json.dumps({"monday": [{"start": "09:00", "end": "17:00"}]})
    db_session.add(owner)
    db_session.commit()

    response = client.get("/i18n-biz", cookies={"access_token": access_token}) # Session cookie should persist locale
    assert response.status_code == 200
    assert "احجز خدمة" in response.text # Arabic translation

    # Change language to French
    response = client.get("/set_language/fr?redirect_to=/i18n-biz", cookies={"access_token": access_token}, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers['location'] == "/i18n-biz"

    response = client.get("/i18n-biz", cookies={"access_token": access_token})
    assert response.status_code == 200
    assert "Réserver un Service" in response.text # French translation
