import pytest
from httpx import AsyncClient
from sqlalchemy.orm import Session
from src.main import app
from src import models, security, schemas
from src.database import Base, engine, get_db
from datetime import date, time, timedelta
import asyncio

# Setup test database
@pytest.fixture(scope="module")
def setup_test_db():
    # Ensure tables are created before tests run
    Base.metadata.create_all(bind=engine)
    yield
    # Clean up after tests (optional, depending on test strategy)
    Base.metadata.drop_all(bind=engine)

# Override get_db for testing
@pytest.fixture(scope="function")
def test_db_session(setup_test_db):
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)
    
    # Create a test owner for authentication
    hashed_password = security.get_password_hash("testpassword")
    test_owner = models.Owner(
        name="Test Owner", email="test@example.com", hashed_password=hashed_password,
        phone="1234567890", currency="USD", username="testowner", company_name="Test Co.", is_admin=False
    )
    session.add(test_owner)
    
    # Create an admin owner for testing access control
    admin_hashed_password = security.get_password_hash("adminpassword")
    admin_owner = models.Owner(
        name="Admin User", email="admin@example.com", hashed_password=admin_hashed_password,
        phone="1112223333", currency="USD", username="adminuser", company_name="Admin Co.", is_admin=True
    )
    session.add(admin_owner)

    # Create a second owner for access control tests
    hashed_password_2 = security.get_password_hash("password2")
    owner2 = models.Owner(
        name="Owner Two", email="owner2@example.com", hashed_password=hashed_password_2,
        phone="9876543210", currency="EUR", username="owner2", company_name="Second Co.", is_admin=False
    )
    session.add(owner2)

    # Create a test customer for authentication
    hashed_customer_password = security.get_password_hash("customerpassword")
    test_customer = models.Customer(
        name="Test Customer", email="customer@example.com", hashed_password=hashed_customer_password,
        phone="0987654321"
    )
    session.add(test_customer)

    # Create a second customer for IDOR tests
    hashed_password_3 = security.get_password_hash("customerpassword2")
    customer2 = models.Customer(
        name="Customer Two", email="customer2@example.com", hashed_password=hashed_password_3,
        phone="5551234567"
    )
    session.add(customer2)

    session.commit()
    session.refresh(test_owner)
    session.refresh(admin_owner)
    session.refresh(owner2)
    session.refresh(test_customer)
    session.refresh(customer2)

    def override_get_db():
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    yield session
    session.close()
    transaction.rollback()
    connection.close()
    app.dependency_overrides = {}

@pytest.fixture(scope="function")
async def client(test_db_session):
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client

@pytest.fixture(scope="function")
async def authenticated_owner_client(client: AsyncClient, test_db_session: Session):
    # Authenticate the test owner
    owner = test_db_session.query(models.Owner).filter(models.Owner.email == "test@example.com").first()
    response = await client.post("/token", data={"username": owner.email, "password": "testpassword"})
    token = response.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    return client

@pytest.fixture(scope="function")
async def authenticated_admin_client(client: AsyncClient, test_db_session: Session):
    # Authenticate the admin owner
    admin_owner = test_db_session.query(models.Owner).filter(models.Owner.email == "admin@example.com").first()
    response = await client.post("/token", data={"username": admin_owner.email, "password": "adminpassword"})
    token = response.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    return client

@pytest.fixture(scope="function")
async def authenticated_customer_client(client: AsyncClient, test_db_session: Session):
    # Authenticate the test customer
    customer = test_db_session.query(models.Customer).filter(models.Customer.email == "customer@example.com").first()
    response = await client.post("/customer-token", data={"username": customer.email, "password": "customerpassword"})
    token = response.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    return client

# --- Security Tests ---

@pytest.mark.asyncio
async def test_sql_injection_in_login(client: AsyncClient):
    """Test for SQL Injection in login username/password fields."""
    payloads = [
        {"username": "admin' OR '1'='1", "password": "password"},
        {"username": "admin", "password": "' OR '1'='1"},
        {"username": "admin' --", "password": "password"},
        {"username": "test@example.com' OR 1=1 --", "password": "anypass"}
    ]
    for payload in payloads:
        response = await client.post("/token", data=payload)
        # We expect authentication to fail, not to gain unauthorized access
        assert response.status_code == 401
        assert "Incorrect username or password" in response.json()["detail"]

@pytest.mark.asyncio
async def test_xss_in_owner_profile_update(authenticated_owner_client: AsyncClient, test_db_session: Session):
    """Test for XSS in owner profile update fields (company_name)."""
    xss_payload = "<script>alert('XSS')</script>" # Malicious script
    owner = test_db_session.query(models.Owner).filter(models.Owner.email == "test@example.com").first()
    
    form_data = {
        "name": owner.name,
        "email": owner.email,
        "phone": owner.phone,
        "currency": owner.currency,
        "username": owner.username, 
        "company_name": xss_payload
    }
    response = await authenticated_owner_client.post("/dashboard/profile", data=form_data, follow_redirects=False)
    
    # Expect a redirect on success, indicating the backend processed the request.
    # The key is whether the payload is stored raw or sanitized/validated.
    assert response.status_code == 303 
    updated_owner = test_db_session.query(models.Owner).filter(models.Owner.id == owner.id).first()
    
    # This asserts that the backend stores the XSS payload as-is, indicating a potential client-side XSS vulnerability.
    # Further steps would involve input sanitization on the backend or output encoding on the frontend.
    assert updated_owner.company_name == xss_payload

@pytest.mark.asyncio
async def test_broken_access_control_regular_owner_access_admin_endpoint(authenticated_owner_client: AsyncClient):
    """Test that a regular owner cannot access an admin-only endpoint."""
    response = await authenticated_owner_client.get("/admin/owners")
    assert response.status_code == 403 # Expected Forbidden if admin role is checked
    assert "Not authorized to access admin panel" in response.json()["detail"]

@pytest.mark.asyncio
async def test_broken_authentication_invalid_token(client: AsyncClient):
    """Test API endpoints with an invalid JWT token."""
    response = await client.get("/dashboard", headers={"Authorization": "Bearer invalid_token"})
    assert response.status_code == 401
    assert "Could not validate credentials" in response.json()["detail"]

@pytest.mark.asyncio
async def test_broken_authentication_missing_token(client: AsyncClient):
    """Test API endpoints without any JWT token (expecting authentication required)."""
    response = await client.get("/dashboard") 
    assert response.status_code == 401
    # FastAPI's OAuth2PasswordBearer typically returns this detail for missing token
    assert "Not authenticated" in response.json()["detail"]

@pytest.mark.asyncio
async def test_idor_customer_cancel_other_customer_booking(authenticated_customer_client: AsyncClient, test_db_session: Session):
    """Test for Insecure Direct Object Reference (IDOR) where one customer tries to cancel another's booking."""
    # Get owners and services from the test session
    owner = test_db_session.query(models.Owner).filter(models.Owner.email == "test@example.com").first()
    service = models.Service(owner_id=owner.id, name="Test Service for IDOR", description="Desc", duration_minutes=60, price=10.0)
    test_db_session.add(service)
    test_db_session.commit()
    test_db_session.refresh(service)

    # Get customer2 (the target for IDOR)
    customer2 = test_db_session.query(models.Customer).filter(models.Customer.email == "customer2@example.com").first()

    # Create a booking for customer2
    booking_for_customer2 = models.Booking(
        owner_id=owner.id, service_id=service.id, customer_id=customer2.id,
        customer_name=customer2.name, customer_email=customer2.email,
        date=date.today() + timedelta(days=7), time=time(14,0), is_recurring=False
    )
    test_db_session.add(booking_for_customer2)
    test_db_session.commit()
    test_db_session.refresh(booking_for_customer2)

    # Now, authenticated_customer_client (customer1) tries to cancel booking_for_customer2
    response = await authenticated_customer_client.delete(f"/api/customer/bookings/{booking_for_customer2.id}")
    
    # Expect a 403 Forbidden because customer1 is not the owner of booking_for_customer2
    assert response.status_code == 403 
    assert "Not authorized to cancel this booking" in response.json()["detail"]

    # Verify the booking still exists
    remaining_booking = test_db_session.query(models.Booking).filter(models.Booking.id == booking_for_customer2.id).first()
    assert remaining_booking is not None

@pytest.mark.asyncio
async def test_rate_limiting_login_attempts_placeholder(client: AsyncClient):
    """Placeholder test for rate limiting on login attempts."""
    # This test currently only verifies that the login endpoint remains accessible 
    # and returns 401 for failed attempts after multiple tries. 
    # An actual rate limiting implementation would change the expected status code to 429 (Too Many Requests).
    
    # Simulate multiple failed login attempts
    for i in range(10): # More than a typical hypothetical rate limit
        response = await client.post("/token", data={
            "username": f"nonexistent_user_{i}@example.com", 
            "password": "wrongpassword"
        })
        assert response.status_code == 401 # Still Unauthorized
        # If rate limiting was implemented, after a certain number of requests, 
        # this would become assert response.status_code == 429
