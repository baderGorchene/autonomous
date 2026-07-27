import pytest
from fastapi.testclient import TestClient
from fastapi import status
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.main import app, get_db
from src.database import Base
from src import models, schemas, crud, security
from unittest.mock import patch, MagicMock
import json

# Create a test client
client = TestClient(app)

# Mock SendGrid and Twilio to prevent actual external calls during tests
@pytest.fixture(autouse=True)
def mock_notifications():
    with patch('src.notifications.SendGridAPIClient') as mock_sendgrid, \
         patch('src.notifications.Client') as mock_twilio:
        yield mock_sendgrid, mock_twilio

# Override settings for testing (e.g., use an in-memory SQLite database)
@pytest.fixture(name="test_db")
def override_get_db_fixture():
    SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db" # Use a temporary test database
    engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    Base.metadata.create_all(bind=engine) # Create tables
    
    def get_test_db():
        try:
            db = TestingSessionLocal()
            yield db
        finally:
            db.close()
    
    app.dependency_overrides[get_db] = get_test_db # Override the dependency
    yield
    app.dependency_overrides.pop(get_db) # Clean up the override
    Base.metadata.drop_all(bind=engine) # Drop tables after tests

@pytest.fixture(name="test_owner")
def create_test_owner(test_db):
    db = next(get_db())
    owner_in = schemas.OwnerCreate(
        name="Test Owner",
        email="test@example.com",
        password="testpassword",
        business_name="Test Business",
        slug="test-business",
        phone="+1234567890"
    )
    owner = crud.create_owner(db, owner_in)
    yield owner
    # Cleanup is handled by drop_all in test_db fixture

@pytest.fixture(name="authenticated_client")
def authenticated_client_fixture(test_owner):
    # Login the test owner
    response = client.post("/login", data={
        "email": test_owner.email,
        "password": "testpassword"
    }, follow_redirects=False)
    assert response.status_code == status.HTTP_302_FOUND
    
    # Extract session cookie
    session_cookie = response.cookies.get("session")
    
    # Create a new client that carries the session cookie
    authenticated_client_instance = TestClient(app)
    authenticated_client_instance.cookies.set("session", session_cookie)
    return authenticated_client_instance

def test_health_check():
    response = client.get("/health")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"status": "ok"}

def test_create_owner(test_db):
    owner_in = schemas.OwnerCreate(
        name="New Owner",
        email="new@example.com",
        password="newpassword",
        business_name="New Business",
        slug="new-business",
        phone="+1122334455"
    )
    db = next(get_db())
    owner = crud.create_owner(db, owner_in)
    assert owner.email == owner_in.email
    assert owner.business_name == owner_in.business_name
    assert security.verify_password("newpassword", owner.hashed_password)

def test_owner_signup_success(test_db):
    response = client.post("/signup", data={
        "name": "Signup Test",
        "email": "signup@example.com",
        "password": "signuppassword",
        "business_name": "Signup Biz",
        "slug": "signup-biz",
        "phone": "+1987654321"
    }, follow_redirects=False)
    assert response.status_code == status.HTTP_302_FOUND # Redirect to dashboard
    db = next(get_db())
    owner = crud.get_owner_by_email(db, email="signup@example.com")
    assert owner is not None
    assert owner.slug == "signup-biz"

def test_owner_signup_duplicate_email(test_owner):
    response = client.post("/signup", data={
        "name": "Duplicate User",
        "email": test_owner.email, # Duplicate email
        "password": "password",
        "business_name": "Duplicate Business",
        "slug": "duplicate-biz"
    }, follow_redirects=True)
    assert "Email already registered" in response.text
    assert response.status_code == status.HTTP_200_OK # Renders signup page with error

def test_owner_signup_duplicate_slug(test_owner):
    response = client.post("/signup", data={
        "name": "Another User",
        "email": "another@example.com",
        "password": "password",
        "business_name": "Another Business",
        "slug": test_owner.slug # Duplicate slug
    }, follow_redirects=True)
    assert "Business URL already taken" in response.text
    assert response.status_code == status.HTTP_200_OK # Renders signup page with error

def test_owner_login_success(test_owner):
    response = client.post("/login", data={
        "email": test_owner.email,
        "password": "testpassword"
    }, follow_redirects=False)
    assert response.status_code == status.HTTP_302_FOUND
    assert response.headers["location"] == "/dashboard"
    assert "session" in response.cookies

def test_owner_login_bad_credentials(test_db):
    response = client.post("/login", data={
        "email": "nonexistent@example.com",
        "password": "wrongpassword"
    }, follow_redirects=True)
    assert "Incorrect email or password" in response.text
    assert response.status_code == status.HTTP_200_OK

def test_owner_logout(authenticated_client):
    response = authenticated_client.get("/logout", follow_redirects=False)
    assert response.status_code == status.HTTP_302_FOUND
    assert response.headers["location"] == "/login"
    # Verify session cookie is cleared (or expired)
    assert "session" not in response.cookies or response.cookies["session"] == ""

def test_dashboard_access_authenticated(authenticated_client):
    response = authenticated_client.get("/dashboard")
    assert response.status_code == status.HTTP_200_OK
    assert "Dashboard" in response.text
    assert "Test Business" in response.text # Check if owner data is displayed

def test_dashboard_access_unauthenticated(test_db):
    response = client.get("/dashboard", follow_redirects=False)
    assert response.status_code == status.HTTP_302_FOUND # Should redirect to /login
    assert response.headers["location"] == "/login"

def test_public_booking_page_renders(test_owner):
    response = client.get(f"/bookslot/{test_owner.slug}")
    assert response.status_code == status.HTTP_200_OK
    assert test_owner.business_name in response.text
    assert "Book an Appointment" in response.text # Check for form elements

def test_public_booking_page_not_found(test_db):
    response = client.get("/bookslot/non-existent-slug")
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert "Booking page not found" in response.text

def test_submit_booking_success(test_owner, mock_notifications):
    # Update owner with services and availability
    db = next(get_db())
    test_owner.services_json = json.dumps([{"name": "Haircut", "description": "Standard haircut", "duration_minutes": 30, "price": 25.0}])
    test_owner.availability_json = json.dumps({
        "Monday": [{"day_of_week": "Monday", "start_time": "09:00", "end_time": "17:00"}]
    })
    db.add(test_owner)
    db.commit()
    db.refresh(test_owner)
    
    response = client.post(f"/bookslot/{test_owner.slug}", data={
        "customer_name": "Jane Doe",
        "customer_email": "jane@example.com",
        "customer_phone": "+15551234567",
        "service_name": "Haircut",
        "booking_date": "2024-07-29",
        "booking_time": "10:00"
    }, follow_redirects=True) # follow_redirects=True to get to confirmation page
    
    assert response.status_code == status.HTTP_200_OK
    assert "Booking Confirmed!" in response.text
    assert "Jane Doe" in response.text
    assert "Haircut" in response.text
    assert "2024-07-29" in response.text
    assert "10:00" in response.text

    # Verify notifications were called
    mock_notifications[0].return_value.send.assert_called() # SendGrid
    mock_notifications[1].return_value.messages.create.assert_called() # Twilio

    # Verify booking is in DB
    db = next(get_db())
    booking = db.query(models.Booking).filter_by(customer_email="jane@example.com").first()
    assert booking is not None
    assert booking.service_name == "Haircut"

def test_submit_booking_error_handling(test_owner):
    # Simulate an error by not providing a required field
    response = client.post(f"/bookslot/{test_owner.slug}", data={
        "customer_name": "Jane Doe",
        "customer_email": "jane@example.com",
        # Missing service_name
        "booking_date": "2024-07-29",
        "booking_time": "10:00"
    }, follow_redirects=True)
    
    # Expect to be redirected back to the booking page with an error
    assert response.status_code == status.HTTP_200_OK
    assert "Error processing booking" in response.text # FastAPI form parsing error

def test_owner_profile_view(authenticated_client, test_owner):
    response = authenticated_client.get("/profile")
    assert response.status_code == status.HTTP_200_OK
    assert "Update Your Profile" in response.text
    assert test_owner.name in response.text
    assert test_owner.email in response.text
    assert test_owner.business_name in response.text
    assert test_owner.slug in response.text
    assert test_owner.phone in response.text if test_owner.phone else ""

def test_owner_profile_update_success(authenticated_client, test_owner):
    new_name = "Updated Name"
    new_business_name = "Updated Business"
    new_phone = "+19998887777"
    new_services = [{"name": "New Service", "description": "Desc", "duration_minutes": 60, "price": 50.0}]
    new_availability = {"Wednesday": [{"day_of_week": "Wednesday", "start_time": "11:00", "end_time": "19:00"}]}

    response = authenticated_client.post("/profile", data={
        "name": new_name,
        "business_name": new_business_name,
        "phone": new_phone,
        "services_data": json.dumps(new_services),
        "availability_data": json.dumps(new_availability)
    }, follow_redirects=False)
    
    assert response.status_code == status.HTTP_302_FOUND
    assert response.headers["location"] == "/dashboard?message=Profile updated successfully"

    db = next(get_db())
    updated_owner = crud.get_owner(db, test_owner.id)
    assert updated_owner.name == new_name
    assert updated_owner.business_name == new_business_name
    assert updated_owner.phone == new_phone
    assert json.loads(updated_owner.services_json) == new_services
    assert json.loads(updated_owner.availability_json) == new_availability

def test_owner_profile_update_invalid_json(authenticated_client, test_owner):
    response = authenticated_client.post("/profile", data={
        "name": "Name",
        "business_name": "Business",
        "phone": "",
        "services_data": "invalid json",
        "availability_data": "{}"
    }, follow_redirects=True) # follow_redirects to see the error on the profile page
    
    assert response.status_code == status.HTTP_200_OK
    assert "Invalid JSON for services or availability." in response.text

def test_owner_profile_update_invalid_service_schema(authenticated_client, test_owner):
    invalid_services = [{"name": "Invalid Service", "duration_minutes": "not_an_int"}] # Invalid duration
    response = authenticated_client.post("/profile", data={
        "name": "Name",
        "business_name": "Business",
        "phone": "",
        "services_data": json.dumps(invalid_services),
        "availability_data": "{}"
    }, follow_redirects=True)
    
    assert response.status_code == status.HTTP_200_OK
    assert "An error occurred" in response.text # Pydantic validation error
    assert "value is not a valid integer" in response.text
