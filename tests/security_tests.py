import pytest
from httpx import AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.models import Base, Owner, Service, Booking, Customer
from src.security import get_password_hash, create_access_token
from src.main import app
from src.database import get_db as get_app_db # Alias to avoid conflict with fixture
from datetime import date, time, timedelta

# --- Test Database Setup ---
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
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
async def client_fixture(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass # Session is closed by db_session_fixture

    app.dependency_overrides[get_app_db] = override_get_db
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()

# --- Helper functions for tests ---
def create_test_owner(db, email="test@example.com", password="password123", name="Test Owner"):
    hashed_password = get_password_hash(password)
    owner = Owner(email=email, hashed_password=hashed_password, name=name)
    db.add(owner)
    db.commit()
    db.refresh(owner)
    return owner

def create_test_service(db, owner_id, name="Test Service"):
    service = Service(owner_id=owner_id, name=name, duration_minutes=60, price=50)
    db.add(service)
    db.commit()
    db.refresh(service)
    return service

def get_owner_token(email="test@example.com"):
    return create_access_token(data={"sub": email}, expires_delta=timedelta(minutes=60))

# --- Security Tests ---

@pytest.mark.asyncio
async def test_sql_injection_login_attempt(client, db_session):
    create_test_owner(db_session, email="admin@bookslot.app", password="securepassword")

    payloads = [
        "' OR '1'='1 --",
        "admin' #",
        "admin' UNION SELECT NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL --", # Attempt union-based
        "admin' AND 1=DBMS_PIPE.RECEIVE_MESSAGE('a',10) --", # Time-based blind
    ]

    for payload in payloads:
        response = await client.post(
            "/login",
            data={"username": payload, "password": "anypassword"}
        )
        assert response.status_code == 401
        assert "Incorrect username or password" in response.json()["detail"]

@pytest.mark.asyncio
async def test_xss_in_booking_customer_name(client, db_session):
    owner = create_test_owner(db_session)
    service = create_test_service(db_session, owner.id)
    token = get_owner_token(owner.email)

    xss_payloads = [
        "<script>alert('XSS')</script>",
        '"><img src=x onerror=alert(1)>',
        "<body onload=alert('XSS')>",
        "<iframe src='javascript:alert("XSS")'></iframe>",
    ]

    for payload in xss_payloads:
        booking_data = {
            "service_id": service.id,
            "customer_name": payload,
            "customer_email": "xss@example.com",
            "date": str(date.today() + timedelta(days=1)),
            "time": "10:00:00",
        }
        response = await client.post(
            "/bookings/",
            json=booking_data,
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 400
        assert "Invalid customer name format." in response.json()["detail"]

@pytest.mark.asyncio
async def test_broken_authentication_brute_force_no_rate_limit_check(client, db_session):
    create_test_owner(db_session, email="brute@example.com", password="correctpassword")
    
    # Simulate multiple failed login attempts
    for i in range(15): # More than a typical threshold for simple rate limiting
        response = await client.post(
            "/login",
            data={"username": "brute@example.com", "password": f"wrongpass{i}"}
        )
        assert response.status_code == 401
    
    # After multiple failures, try with the correct password
    response = await client.post(
        "/login",
        data={"username": "brute@example.com", "password": "correctpassword"}
    )
    # This test currently passes with 200, highlighting that explicit rate limiting
    # or account lockout mechanisms are not yet implemented for the login endpoint.
    assert response.status_code == 200
    assert "access_token" in response.json()

@pytest.mark.asyncio
async def test_broken_access_control_idor_booking_service(client, db_session):
    owner1 = create_test_owner(db_session, email="owner1@example.com", password="password1")
    owner2 = create_test_owner(db_session, email="owner2@example.com", password="password2")
    service2 = create_test_service(db_session, owner2.id, name="Owner2's Service") # Service belonging to owner2

    token1 = get_owner_token(owner1.email)

    # Attempt for owner1 to book a service belonging to owner2 (IDOR)
    booking_data = {
        "service_id": service2.id,
        "customer_name": "Intruder",
        "customer_email": "intruder@example.com",
        "date": str(date.today() + timedelta(days=1)),
        "time": "11:00:00",
    }
    response = await client.post(
        "/bookings/",
        json=booking_data,
        headers={"Authorization": f"Bearer {token1}"}
    )
    # With the fix in main.py, this should now correctly return 404
    assert response.status_code == 404
    assert "Service not found or not owned by you." in response.json()["detail"]

@pytest.mark.asyncio
async def test_input_validation_overflow_booking_name(client, db_session):
    owner = create_test_owner(db_session)
    service = create_test_service(db_session, owner.id)
    token = get_owner_token(owner.email)

    long_name = "A" * 200 # Exceeds the 100 char limit in main.py
    booking_data = {
        "service_id": service.id,
        "customer_name": long_name,
        "customer_email": "longname@example.com",
        "date": str(date.today() + timedelta(days=1)),
        "time": "12:00:00",
    }
    response = await client.post(
        "/bookings/",
        json=booking_data,
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 400
    assert "Invalid customer name format." in response.json()["detail"]

@pytest.mark.asyncio
async def test_input_validation_invalid_email_format(client, db_session):
    owner = create_test_owner(db_session)
    service = create_test_service(db_session, owner.id)
    token = get_owner_token(owner.email)

    booking_data = {
        "service_id": service.id,
        "customer_name": "Invalid Email Test",
        "customer_email": "invalid-email-format", # Malformed email
        "date": str(date.today() + timedelta(days=1)),
        "time": "13:00:00",
    }
    response = await client.post(
        "/bookings/",
        json=booking_data,
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 422
    assert "Invalid input provided." in response.json()["detail"]

@pytest.mark.asyncio
async def test_unauthenticated_access_to_protected_endpoint(client):
    response = await client.get("/owner/me")
    assert response.status_code == 401
    assert "Could not validate credentials" in response.json()["detail"]

@pytest.mark.asyncio
async def test_invalid_token_access_to_protected_endpoint(client):
    response = await client.get(
        "/owner/me",
        headers={"Authorization": "Bearer invalid_token"}
    )
    assert response.status_code == 401
    assert "Could not validate credentials" in response.json()["detail"]
