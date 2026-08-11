import pytest
from httpx import AsyncClient
from sqlalchemy.orm import Session
from src.database import get_db
from src.main import app
from src.models import Owner, Service, Customer, Booking
from src.security import create_access_token, hash_password
from datetime import datetime, timedelta, date, time

# Helper function to get a test database session
@pytest.fixture(name="db_session")
def db_session_fixture():
    db = next(get_db())
    # Clear tables for a clean test environment (adjust as necessary)
    db.query(Booking).delete()
    db.query(Customer).delete()
    db.query(Service).delete()
    db.query(Owner).delete()
    db.commit()
    yield db
    db.rollback() # Ensure rollback after tests

@pytest.fixture(name="test_client")
async def test_client_fixture():
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client

@pytest.fixture
def test_owner(db_session: Session):
    owner = Owner(
        email="test@example.com",
        hashed_password=hash_password("testpassword"),
        name="Test Owner",
        phone="+1234567890",
        currency="USD",
        timezone="UTC",
        username="testowner"
    )
    db_session.add(owner)
    db_session.commit()
    db_session.refresh(owner)
    return owner

@pytest.fixture
def test_service(db_session: Session, test_owner: Owner):
    service = Service(
        owner_id=test_owner.id,
        name="Test Service",
        description="A test service.",
        duration_minutes=30,
        price=50.0
    )
    db_session.add(service)
    db_session.commit()
    db_session.refresh(service)
    return service

@pytest.fixture
def owner_auth_headers(test_owner: Owner):
    access_token = create_access_token(data={"sub": test_owner.email, "scope": "owner"})
    return {"Authorization": f"Bearer {access_token}"}

# --- SQL Injection Tests ---
@pytest.mark.asyncio
async def test_sql_injection_login(test_client: AsyncClient):
    # Test with common SQL injection payloads in email and password
    sqli_payloads = [
        "' OR '1'='1",
        "' OR '1'='1' --",
        "admin'--",
        "admin' #",
        "admin') OR ('1'='1",
        "admin' AND 1=1 --",
    ]
    for payload in sqli_payloads:
        response = await test_client.post(
            "/token",
            data={"username": payload, "password": "anypassword"}
        )
        # Expect login to fail, not succeed due to injection
        assert response.status_code in [400, 401, 422], f"SQLi payload '{payload}' might have worked on login"
        assert "Incorrect username or password" in response.text or "validation error" in response.text

@pytest.mark.asyncio
async def test_sql_injection_booking_data(test_client: AsyncClient, db_session: Session, test_owner: Owner, test_service: Service):
    # Simulate a booking with SQLi payloads in customer details
    sqli_payloads = [
        "john@example.com' OR '1'='1",
        "O'Malley",
        "Robert'); DROP TABLE users; --",
        "test@example.com; SELECT SLEEP(5);",
        "<script>alert('SQLi via XSS')</script>", # Also test combined payloads
        "union select null,null,null,null,null,null,null,null,null --",
        "' and (select 1 from pg_sleep(2)) and '1'='1", # Time-based blind SQLi
    ]
    for payload in sqli_payloads:
        booking_data = {
            "customer_name": payload,
            "customer_email": "sqli_test@example.com", # Use a fixed email to avoid multiple customer creations
            "customer_phone": "+1234567890",
            "date": (date.today() + timedelta(days=1)).isoformat(),
            "time": "10:00:00",
            "recurrence_type": "NONE"
        }
        response = await test_client.post(
            f"/book/{test_owner.username}/{test_service.id}",
            json=booking_data
        )
        # Expect validation errors or normal booking flow, not database errors or unexpected success
        assert response.status_code in [200, 422, 404], f"SQLi payload '{payload}' might have worked on booking"
        assert "Database error" not in response.text # Ensure no direct DB error messages are exposed
        assert "internal server error" not in response.text # Generic server error should not be caused by simple payload

    # Verify no unexpected customers or bookings were created due to SQLi
    customers = db_session.query(Customer).filter(Customer.email == "sqli_test@example.com").all()
    bookings = db_session.query(Booking).filter(Booking.customer_email == "sqli_test@example.com").all()
    # We expect at most one customer and one booking if the first valid-looking payload was processed.
    # The goal is to ensure SQLi payloads don't lead to errors or data manipulation.
    assert len(customers) <= 1
    assert len(bookings) <= 1

# --- XSS Tests ---
@pytest.mark.asyncio
async def test_xss_booking_page_customer_name(test_client: AsyncClient, db_session: Session, test_owner: Owner, test_service: Service):
    # Test XSS in customer name field
    xss_payloads = [
        "<script>alert('XSS')</script>",
        "\"'><img src=x onerror=alert('XSS')>",
        "<svg/onload=alert('XSS')>",
        "onmouseover=alert(1) //",
        "<!--<script>alert('XSS')</script>-->",
        "<body onload=alert('XSS')>",
        "<iframe src=javascript:alert('XSS')></iframe>",
        "<input type='image' src='javascript:alert('XSS')'>",
        "<details open ontoggle=alert('XSS')>",
        "<marquee onstart=alert('XSS')>",
    ]
    for i, payload in enumerate(xss_payloads):
        booking_data = {
            "customer_name": payload,
            "customer_email": f"xss_test_{i}@example.com",
            "customer_phone": "+1234567890",
            "date": (date.today() + timedelta(days=1)).isoformat(),
            "time": "10:00:00",
            "recurrence_type": "NONE"
        }
        response = await test_client.post(
            f"/book/{test_owner.username}/{test_service.id}",
            json=booking_data
        )
        # Expect successful booking or validation error, but not an XSS vulnerability on the confirmation page
        assert response.status_code in [200, 422, 404], f"XSS payload '{payload}' on booking submission failed unexpectedly"

        # If booking was successful, retrieve the confirmation page and check for payload
        if response.status_code == 200:
            # Assuming the confirmation page might display the customer name
            # The actual URL for confirmation might be a redirect or a direct response.
            # For robustness, we check the response content itself.
            assert payload not in response.text, f"XSS payload '{payload}' found unescaped in booking confirmation"
            # If there's a redirect, we'd need to follow it and check its content
            if response.is_redirect:
                confirmation_response = await test_client.get(response.headers["Location"])
                assert payload not in confirmation_response.text, f"XSS payload '{payload}' found unescaped after redirect"

@pytest.mark.asyncio
async def test_xss_owner_profile_update(test_client: AsyncClient, test_owner: Owner, owner_auth_headers: dict):
    xss_payload = "<script>alert('XSS-owner')</script>"
    update_data = {
        "name": xss_payload,
        "phone": test_owner.phone,
        "currency": test_owner.currency,
        "timezone": test_owner.timezone
    }
    response = await test_client.put(
        "/owner/profile",
        json=update_data,
        headers=owner_auth_headers
    )
    assert response.status_code in [200, 422] # Expect success or validation error

    if response.status_code == 200:
        # Verify that the payload is not rendered unescaped on the dashboard
        dashboard_response = await test_client.get("/owner/dashboard", headers=owner_auth_headers)
        assert xss_payload not in dashboard_response.text

@pytest.mark.asyncio
async def test_xss_service_description(test_client: AsyncClient, test_owner: Owner, owner_auth_headers: dict):
    xss_payload = "<img src=x onerror=alert('XSS-service')>"
    service_data = {
        "name": "XSS Service",
        "description": xss_payload,
        "duration_minutes": 60,
        "price": 100.0
    }
    response = await test_client.post(
        "/owner/services",
        json=service_data,
        headers=owner_auth_headers
    )
    assert response.status_code == 200
    service_id = response.json()["id"]

    # Check if XSS is present on the public booking page for this service
    public_page_response = await test_client.get(f"/{test_owner.username}")
    assert xss_payload not in public_page_response.text

    # Check if XSS is present on the owner dashboard when viewing services
    dashboard_response = await test_client.get("/owner/dashboard", headers=owner_auth_headers)
    assert xss_payload not in dashboard_response.text

# --- Broken Authentication/Authorization Tests ---
@pytest.mark.asyncio
async def test_unauthenticated_access_to_dashboard(test_client: AsyncClient):
    response = await test_client.get("/owner/dashboard")
    assert response.status_code == 401
    assert "Not authenticated" in response.text

@pytest.mark.asyncio
async def test_invalid_token_access_to_dashboard(test_client: AsyncClient):
    invalid_headers = {"Authorization": "Bearer invalid_token"}
    response = await test_client.get("/owner/dashboard", headers=invalid_headers)
    assert response.status_code == 401
    assert "Could not validate credentials" in response.text

@pytest.mark.asyncio
async def test_customer_access_owner_dashboard(test_client: AsyncClient, db_session: Session):
    # Create a customer and get their token
    customer = Customer(
        email="customer@example.com",
        hashed_password=hash_password("customerpassword"),
        name="Test Customer",
        phone="+1111111111"
    )
    db_session.add(customer)
    db_session.commit()
    db_session.refresh(customer)
    customer_access_token = create_access_token(data={"sub": customer.email, "scope": "customer"})
    customer_headers = {"Authorization": f"Bearer {customer_access_token}"}

    response = await test_client.get("/owner/dashboard", headers=customer_headers)
    # A customer should not be able to access the owner dashboard
    assert response.status_code == 403 # Forbidden due to scope
    assert "Not authorized to access this resource" in response.text

@pytest.mark.asyncio
async def test_owner_access_other_owners_data(test_client: AsyncClient, db_session: Session, test_owner: Owner, owner_auth_headers: dict):
    # Create a second owner and service
    other_owner = Owner(
        email="other@example.com",
        hashed_password=hash_password("otherpassword"),
        name="Other Owner",
        phone="+1987654321",
        currency="EUR",
        timezone="Europe/Berlin",
        username="otherowner"
    )
    db_session.add(other_owner)
    db_session.commit()
    db_session.refresh(other_owner)

    other_service = Service(
        owner_id=other_owner.id,
        name="Other Service",
        description="Another test service.",
        duration_minutes=60,
        price=100.0
    )
    db_session.add(other_service)
    db_session.commit()
    db_session.refresh(other_service)

    # Attempt to access/modify other_owner's service using test_owner's token
    response = await test_client.get(
        f"/owner/services/{other_service.id}",
        headers=owner_auth_headers
    )
    assert response.status_code == 404 # Should not find a service belonging to another owner
    assert "Service not found" in response.text # Or explicit authorization error

    # Attempt to delete other_owner's service
    response = await test_client.delete(
        f"/owner/services/{other_service.id}",
        headers=owner_auth_headers
    )
    assert response.status_code == 404 # Should not find a service belonging to another owner
    assert "Service not found" in response.text

    # Attempt to update other_owner's service
    update_data = {"name": "Malicious Update", "description": "", "duration_minutes": 30, "price": 10.0}
    response = await test_client.put(
        f"/owner/services/{other_service.id}",
        json=update_data,
        headers=owner_auth_headers
    )
    assert response.status_code == 404

# --- Rate Limiting Tests (Conceptual - requires actual rate limiting implementation) ---
@pytest.mark.asyncio
async def test_rate_limiting_login_conceptual(test_client: AsyncClient):
    # This test is conceptual and assumes a rate-limiting middleware is in place.
    # Without actual rate limiting, it will just succeed/fail based on credentials.
    # To properly test, a rate-limiting library (e.g., `fastapi-limiter`) would be needed.
    
    # Simulate many failed login attempts
    for _ in range(15): # Adjust count based on expected rate limit threshold
        response = await test_client.post(
            "/token",
            data={"username": "nonexistent@example.com", "password": "wrongpassword"}
        )
        # Expect 401 for incorrect credentials, eventually 429 if rate limit is hit
        # For now, we only assert 401/400/422 as rate limiting is not yet implemented.
        assert response.status_code in [400, 401, 422, 429]
        if response.status_code == 429:
            assert "Rate limit exceeded" in response.text
            print("\nRate limit hit during login test.")
            return # Stop if rate limit is hit

    # If no rate limit is hit after many attempts, it indicates it's not implemented or too high
    pytest.fail("Rate limiting for login endpoint might not be implemented or configured correctly. (Conceptual test)")


# --- Input Validation and Edge Cases ---
@pytest.mark.asyncio
async def test_input_validation_long_strings(test_client: AsyncClient, test_owner: Owner, owner_auth_headers: dict):
    long_string = "A" * 500 # Excessively long string, assuming typical limits like 255 for names/emails
    very_long_string = "A" * 2000 # Even longer string for description fields

    # Test in owner profile update
    update_data = {
        "name": long_string, # Should be limited
        "phone": test_owner.phone,
        "currency": test_owner.currency,
        "timezone": test_owner.timezone
    }
    response = await test_client.put(
        "/owner/profile",
        json=update_data,
        headers=owner_auth_headers
    )
    assert response.status_code == 422 # Expect validation error for too long name

    # Test in service creation
    service_data = {
        "name": long_string, # Should be limited
        "description": very_long_string, # Should be limited
        "duration_minutes": 30,
        "price": 50.0
    }
    response = await test_client.post(
        "/owner/services",
        json=service_data,
        headers=owner_auth_headers
    )
    assert response.status_code == 422 # Expect validation error for too long service name/description

    # Test in booking details
    booking_data = {
        "customer_name": long_string,
        "customer_email": "valid@example.com",
        "customer_phone": "+1234567890",
        "date": (date.today() + timedelta(days=1)).isoformat(),
        "time": "10:00:00",
        "recurrence_type": "NONE"
    }
    response = await test_client.post(
        f"/book/{test_owner.username}/{test_service.id}",
        json=booking_data
    )
    assert response.status_code == 422 # Expect validation error for too long customer name

@pytest.mark.asyncio
async def test_input_validation_invalid_email_phone(test_client: AsyncClient, test_owner: Owner, test_service: Service):
    invalid_email_payloads = ["invalid-email", "user@.com", "user@domain", "user@domain.", "user@domain.c", "@", "a@b", "a@b."]
    invalid_phone_payloads = ["123", "abc", "++123", "123456789012345678901234567890", "+1-555-ABC-DEF", "(555) 555-5555x123"]

    for email in invalid_email_payloads:
        booking_data = {
            "customer_name": "Test Customer",
            "customer_email": email,
            "customer_phone": "+1234567890",
            "date": (date.today() + timedelta(days=1)).isoformat(),
            "time": "10:00:00",
            "recurrence_type": "NONE"
        }
        response = await test_client.post(
            f"/book/{test_owner.username}/{test_service.id}",
            json=booking_data
        )
        assert response.status_code == 422, f"Invalid email '{email}' should cause validation error"

    for phone in invalid_phone_payloads:
        booking_data = {
            "customer_name": "Test Customer",
            "customer_email": "valid@example.com",
            "customer_phone": phone,
            "date": (date.today() + timedelta(days=1)).isoformat(),
            "time": "10:00:00",
            "recurrence_type": "NONE"
        }
        response = await test_client.post(
            f"/book/{test_owner.username}/{test_service.id}",
            json=booking_data
        )
        assert response.status_code == 422, f"Invalid phone '{phone}' should cause validation error"

@pytest.mark.asyncio
async def test_input_validation_negative_values(test_client: AsyncClient, test_owner: Owner, owner_auth_headers: dict):
    # Test service creation with negative duration/price
    service_data = {
        "name": "Negative Service",
        "description": "Test negative values",
        "duration_minutes": -30,
        "price": -50.0
    }
    response = await test_client.post(
        "/owner/services",
        json=service_data,
        headers=owner_auth_headers
    )
    assert response.status_code == 422 # Expect validation error

    # Test service creation with zero duration/price (edge case)
    service_data_zero = {
        "name": "Zero Service",
        "description": "Test zero values",
        "duration_minutes": 0,
        "price": 0.0
    }
    response_zero = await test_client.post(
        "/owner/services",
        json=service_data_zero,
        headers=owner_auth_headers
    )
    # Depending on business logic, 0 might be allowed or not. Assuming not for duration.
    assert response_zero.status_code == 422 

# --- Error Handling and Logging (Verifies response, logging is checked via file/console output) ---
@pytest.mark.asyncio
async def test_error_handling_generic_messages(test_client: AsyncClient):
    # Simulate an endpoint that might throw an unexpected error (e.g., non-existent path)
    response = await test_client.get("/nonexistent-path")
    assert response.status_code == 404
    assert "Not Found" in response.text # Should be a generic error, not internal details

    # Simulate an internal server error by accessing an endpoint that is expected to fail
    # This requires a specific endpoint that can be made to fail, for now, we assume 500
    # For a real test, you'd mock a dependency to fail or inject an error.
    # Example: If there's an endpoint that tries to divide by zero or access a non-existent DB column
    # For now, we rely on the generic_exception_handler for unhandled exceptions.
    # If we had a specific endpoint like `/test-internal-error` that explicitly raises an Exception,
    # we would test it like this:
    # response = await test_client.get("/test-internal-error")
    # assert response.status_code == 500
    # assert "An unexpected server error occurred." in response.text
