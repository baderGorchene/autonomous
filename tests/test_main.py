import pytest
from httpx import AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.database import Base
from src.main import app, get_db
from src import models, security, crud, schemas
import datetime
import json
import os

# Use a test database
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Override the get_db dependency for tests
def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

@pytest.fixture(name="test_db")
def test_db_fixture():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

@pytest.fixture(name="client")
async def client_fixture(test_db):
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client

# Helper function for creating an owner and getting a token
async def create_test_owner_and_login(client: AsyncClient, db: TestingSessionLocal, email="test@example.com", password="password123", slug="test-business"):
    owner_data = schemas.OwnerCreate(
        name="Test Owner",
        email=email,
        password=password,
        business_name="Test Business",
        slug=slug
    )
    crud.create_owner(db, owner_data)

    response = await client.post(
        "/token",
        data={"username": email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    assert response.status_code == 200, response.text
    token = response.json().get("access_token")
    return token, email, slug

def get_current_time_for_booking():
    # Get current time and round up to next half hour for booking
    now = datetime.datetime.now()
    if now.minute > 30:
        next_hour = now.replace(minute=0, second=0, microsecond=0) + datetime.timedelta(hours=1)
        booking_time = next_hour.replace(minute=0)
    else:
        booking_time = now.replace(minute=30, second=0, microsecond=0)
    
    # Ensure it's not in the past relative to test execution
    if booking_time <= now:
        booking_time += datetime.timedelta(minutes=30)
    
    return booking_time.strftime("%Y-%m-%d"), booking_time.strftime("%H:%M")

# --- Tests Start Here ---

@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    response = await client.get("/health")
    assert response.status_code == 200
    assert "BookSlot is healthy!" in response.text

@pytest.mark.asyncio
async def test_owner_signup_and_login(client: AsyncClient, test_db):
    # Test signup page render
    response = await client.get("/signup")
    assert response.status_code == 200
    assert "Create Your Account" in response.text

    # Test signup submission
    response = await client.post(
        "/signup",
        data={
            "name": "John Doe",
            "email": "john@example.com",
            "password": "securepassword",
            "business_name": "John's Services",
            "slug": "johns-services"
        },
        follow_redirects=False
    )
    assert response.status_code == 303 # Redirect to login
    assert response.headers["location"] == "/login?message=signup_success"

    # Test login page render
    response = await client.get("/login")
    assert response.status_code == 200
    assert "Log In" in response.text

    # Test login submission
    response = await client.post(
        "/login",
        data={"email": "john@example.com", "password": "securepassword"},
        follow_redirects=False
    )
    assert response.status_code == 303 # Redirect to dashboard
    assert response.headers["location"] == "/dashboard"
    assert "access_token" in response.cookies

    # Test duplicate email signup
    response = await client.post(
        "/signup",
        data={
            "name": "Jane Doe",
            "email": "john@example.com", # Duplicate email
            "password": "securepassword",
            "business_name": "Jane's Services",
            "slug": "janes-services"
        },
        follow_redirects=False
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/signup?error=email_exists"
    
    # Test duplicate slug signup
    response = await client.post(
        "/signup",
        data={
            "name": "Jane Doe",
            "email": "jane@example.com",
            "password": "securepassword",
            "business_name": "Jane's Services",
            "slug": "johns-services" # Duplicate slug
        },
        follow_redirects=False
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/signup?error=slug_exists"

@pytest.mark.asyncio
async def test_owner_dashboard_access_and_profile_update(client: AsyncClient, test_db):
    db = TestingSessionLocal()
    token, email, slug = await create_test_owner_and_login(client, db)
    db.close()

    # Test dashboard access
    response = await client.get("/dashboard", cookies={"access_token": token})
    assert response.status_code == 200
    assert "Welcome, Test Owner!" in response.text
    assert "Your Profile" in response.text

    # Test profile update
    updated_services = [
        {"name": "Haircut", "duration_minutes": 30, "price": "$30"},
        {"name": "Coloring", "duration_minutes": 90, "price": "$100"}
    ]
    updated_availability = [
        {"day_of_week": "Monday", "start_time": "09:00", "end_time": "17:00"},
        {"day_of_week": "Wednesday", "start_time": "10:00", "end_time": "18:00"}
    ]

    response = await client.post(
        "/dashboard/profile",
        data={
            "name": "Updated Owner",
            "business_name": "Updated Business",
            "phone": "+1234567890",
            "services": json.dumps(updated_services),
            "availability": json.dumps(updated_availability)
        },
        cookies={"access_token": token},
        follow_redirects=False
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/dashboard?message=profile_updated"

    # Verify updated profile on dashboard
    response = await client.get("/dashboard", cookies={"access_token": token})
    assert response.status_code == 200
    assert "Welcome, Updated Owner!" in response.text
    assert "Updated Business" in response.text
    assert "+1234567890" in response.text
    assert "Haircut" in response.text
    assert "Coloring" in response.text
    assert "09:00" in response.text
    assert "17:00" in response.text

@pytest.mark.asyncio
async def test_public_booking_page_and_submission(client: AsyncClient, test_db):
    db = TestingSessionLocal()
    token, email, owner_slug = await create_test_owner_and_login(client, db, slug="demo-salon")

    # Update owner with services and availability
    owner = db.query(models.Owner).filter(models.Owner.email == email).first()
    owner.services_json = json.dumps([{"name": "Haircut", "duration_minutes": 30, "price": "$30"}])
    owner.availability_json = json.dumps([{"day_of_week": "Monday", "start_time": "09:00", "end_time": "17:00"}])
    owner.phone = "+15005550006" # Twilio test number
    db.add(owner)
    db.commit()
    db.refresh(owner)
    db.close()

    # Test public booking page render
    response = await client.get(f"/{owner_slug}")
    assert response.status_code == 200
    assert "Book Your Appointment with Test Business" in response.text
    assert "Haircut" in response.text

    # Test booking submission
    booking_date, booking_time = get_current_time_for_booking() # Ensure future time
    
    response = await client.post(
        f"/{owner_slug}/book",
        data={
            "customer_name": "Jane Customer",
            "customer_email": "jane@customer.com",
            "customer_phone": "+15005550006", # Twilio test number
            "service_name": "Haircut",
            "booking_date": booking_date,
            "booking_time": booking_time
        },
        follow_redirects=False
    )
    assert response.status_code == 303
    assert response.headers["location"] == f"/{owner_slug}/confirmation"

    # Verify booking in dashboard
    db = TestingSessionLocal()
    owner_after_booking = db.query(models.Owner).filter(models.Owner.email == email).first()
    token_after_booking, _, _ = await create_test_owner_and_login(client, db, email=owner_after_booking.email, password="password123", slug=owner_after_booking.slug) # Re-login to get fresh token if needed, or use existing
    response = await client.get("/dashboard", cookies={"access_token": token_after_booking})
    assert response.status_code == 200
    assert "Jane Customer" in response.text
    assert "Haircut" in response.text
    assert booking_time in response.text
    db.close()

@pytest.mark.asyncio
async def test_i18n_language_toggle_and_translation(client: AsyncClient, test_db):
    db = TestingSessionLocal()
    token, email, owner_slug = await create_test_owner_and_login(client, db, slug="i18n-test")
    
    # Update owner with services and availability for booking page
    owner = db.query(models.Owner).filter(models.Owner.email == email).first()
    owner.services_json = json.dumps([{"name": "Haircut", "duration_minutes": 30, "price": "$30"}])
    owner.availability_json = json.dumps([{"day_of_week": "Monday", "start_time": "09:00", "end_time": "17:00"}])
    db.add(owner)
    db.commit()
    db.close()

    # Test dashboard in English (default)
    response = await client.get("/dashboard", cookies={"access_token": token})
    assert response.status_code == 200
    assert "Owner Dashboard" in response.text
    assert "Welcome, Test Owner!" in response.text

    # Test dashboard in Arabic
    response = await client.get("/dashboard?lang=ar", cookies={"access_token": token})
    assert response.status_code == 200
    assert "لوحة تحكم المالك" in response.text # Arabic translation for "Owner Dashboard"
    assert "مرحباً، Test Owner!" in response.text # Arabic translation for "Welcome, %s!"
    assert response.cookies["lang"] == "ar"

    # Test dashboard in French
    response = await client.get("/dashboard?lang=fr", cookies={"access_token": token})
    assert response.status_code == 200
    assert "Tableau de bord du propriétaire" in response.text # French translation
    assert "Bienvenue, Test Owner!" in response.text # French translation
    assert response.cookies["lang"] == "fr"

    # Test public booking page in English (default)
    response = await client.get(f"/{owner_slug}")
    assert response.status_code == 200
    assert "Book Your Appointment with Test Business" in response.text

    # Test public booking page in Arabic
    response = await client.get(f"/{owner_slug}?lang=ar")
    assert response.status_code == 200
    assert "احجز موعدك مع Test Business" in response.text # Arabic translation
    assert response.cookies["lang"] == "ar"

    # Test public booking page in French
    response = await client.get(f"/{owner_slug}?lang=fr")
    assert response.status_code == 200
    assert "Réservez votre rendez-vous avec Test Business" in response.text # French translation
    assert response.cookies["lang"] == "fr"

@pytest.mark.asyncio
async def test_booking_error_handling(client: AsyncClient, test_db):
    db = TestingSessionLocal()
    token, email, owner_slug = await create_test_owner_and_login(client, db, slug="error-test")

    # Update owner with services and availability
    owner = db.query(models.Owner).filter(models.Owner.email == email).first()
    owner.services_json = json.dumps([{"name": "Test Service", "duration_minutes": 60, "price": "$50"}])
    owner.availability_json = json.dumps([{"day_of_week": "Monday", "start_time": "09:00", "end_time": "17:00"}])
    db.add(owner)
    db.commit()
    db.close()

    # Test booking for a non-existent owner (FastAPI will return 404 before custom redirect logic)
    response = await client.post(
        "/non-existent-slug/book",
        data={
            "customer_name": "Invalid Customer",
            "customer_email": "invalid@customer.com",
            "service_name": "Test Service",
            "booking_date": "2030-01-01",
            "booking_time": "10:00"
        },
        follow_redirects=False
    )
    assert response.status_code == 404 # FastAPI's default for non-matching route

    # Test booking in the past
    past_date = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    response = await client.post(
        f"/{owner_slug}/book",
        data={
            "customer_name": "Past Customer",
            "customer_email": "past@customer.com",
            "service_name": "Test Service",
            "booking_date": past_date,
            "booking_time": "10:00"
        },
        follow_redirects=False
    )
    assert response.status_code == 303
    assert response.headers["location"] == f"/{owner_slug}?error=past_booking"
    
    # Test profile update with invalid JSON for services/availability
    db = TestingSessionLocal()
    token, _, _ = await create_test_owner_and_login(client, db)
    db.close()
    
    response = await client.post(
        "/dashboard/profile",
        data={
            "name": "Updated Owner",
            "business_name": "Updated Business",
            "phone": "+1234567890",
            "services": "invalid json", # Invalid JSON
            "availability": json.dumps([])
        },
        cookies={"access_token": token},
        follow_redirects=False
    )
    assert response.status_code == 303
    assert "invalid_json_format" in response.headers["location"]
