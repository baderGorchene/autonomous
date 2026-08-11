import pytest
import httpx
from sqlalchemy.exc import StatementError


@pytest.mark.asyncio
async def test_sql_injection_login(client, db_session, test_owner):
    # Attempt SQL injection in username field
    payload = "' OR 1=1 --"
    response = await client.post(
        "/token",
        data={
            "username": payload,
            "password": "wrongpassword"
        }
    )
    # Expect 401 Unauthorized, not a 500 Internal Server Error due to DB issue
    assert response.status_code == httpx.codes.UNAUTHORIZED

    # Attempt SQL injection in password field (less common for direct DB interaction)
    response = await client.post(
        "/token",
        data={
            "username": test_owner.username,
            "password": "' OR 1=1 --"
        }
    )
    assert response.status_code == httpx.codes.UNAUTHORIZED


@pytest.mark.asyncio
async def test_sql_injection_owner_profile_update(client, db_session, test_owner, test_owner_token):
    # Attempt SQL injection in a profile update field (e.g., name)
    payload = "attacker' --"
    response = await client.put(
        f"/owner/profile/{test_owner.id}",
        headers={
            "Authorization": f"Bearer {test_owner_token}"
        },
        json={
            "name": payload,
            "email": test_owner.email,
            "phone": test_owner.phone
        }
    )
    # Expect 200 OK or 422 if validation catches it, but not a DB error
    assert response.status_code == httpx.codes.OK
    updated_owner = (await client.get(
        f"/owner/profile/{test_owner.id}",
        headers={
            "Authorization": f"Bearer {test_owner_token}"
        }
    )).json()
    assert updated_owner["name"] == payload # Ensure the literal string is stored, not executed


@pytest.mark.asyncio
async def test_sql_injection_booking_submission(client, db_session, test_owner, test_service, test_availability):
    # Attempt SQL injection in customer name field
    payload = "evil_customer' OR 1=1 --"
    response = await client.post(
        f"/book/{test_owner.username}/{test_service.id}",
        json={
            "customer_name": payload,
            "customer_email": "customer@example.com",
            "customer_phone": "+1234567890",
            "date": (test_availability.date or (datetime.now().date() + timedelta(days=1))).isoformat(),
            "time": test_availability.start_time.isoformat(),
            "is_recurring": False
        }
    )
    assert response.status_code == httpx.codes.OK # Expect successful booking, literal name stored
    booking_data = response.json()
    assert booking_data["customer_name"] == payload


@pytest.mark.asyncio
async def test_sql_injection_service_creation(client, db_session, test_owner, test_owner_token):
    payload = "New Service' UNION SELECT NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL --"
    response = await client.post(
        f"/owner/services",
        headers={
            "Authorization": f"Bearer {test_owner_token}"
        },
        json={
            "name": payload,
            "description": "A description",
            "duration_minutes": 60,
            "price": 100.00
        }
    )
    assert response.status_code == httpx.codes.CREATED
    service_data = response.json()
    assert service_data["name"] == payload
