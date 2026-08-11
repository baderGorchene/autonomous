import pytest
import httpx
import asyncio
from datetime import datetime, time, timedelta

# NOTE: Rate limiting middleware is typically configured in `main.py`
# and depends on `fastapi-limiter` or similar. This test assumes it's present.
# The `config.py` has `REDIS_URL`, suggesting `fastapi-limiter` might be used.

# Configure these based on your actual rate limiting settings in main.py
LOGIN_RATE_LIMIT = 5 # requests per minute
BOOKING_RATE_LIMIT = 10 # requests per minute


@pytest.mark.asyncio
async def test_rate_limiting_login_endpoint(client, test_owner):
    # Send more requests than the expected rate limit for login
    requests_to_send = LOGIN_RATE_LIMIT + 2
    responses = await asyncio.gather(*[
        client.post(
            "/token",
            data={
                "username": test_owner.username,
                "password": "wrongpassword"
            }
        )
        for _ in range(requests_to_send)
    ], return_exceptions=True)

    unauthorized_count = 0
    too_many_requests_count = 0

    for response in responses:
        if isinstance(response, httpx.Response):
            if response.status_code == httpx.codes.UNAUTHORIZED:
                unauthorized_count += 1
            elif response.status_code == httpx.codes.TOO_MANY_REQUESTS:
                too_many_requests_count += 1

    # Expect at least one 429 response if rate limiting is active
    assert too_many_requests_count >= 1, "Rate limiting did not trigger for login endpoint"
    # Ensure successful logins are not counted as 429
    assert unauthorized_count + too_many_requests_count == requests_to_send


@pytest.mark.asyncio
async def test_rate_limiting_booking_submission_endpoint(client, test_owner, test_service, test_availability):
    booking_date = datetime.now().date() + timedelta(days=1)
    booking_time = time(10, 0)

    # Send more requests than the expected rate limit for booking submission
    requests_to_send = BOOKING_RATE_LIMIT + 2
    responses = await asyncio.gather(*[
        client.post(
            f"/book/{test_owner.username}/{test_service.id}",
            json={
                "customer_name": f"Customer {i}",
                "customer_email": f"customer{i}@example.com",
                "customer_phone": f"+" + str(1000000000 + i),
                "date": booking_date.isoformat(),
                "time": booking_time.isoformat(),
                "is_recurring": False
            }
        )
        for i in range(requests_to_send)
    ], return_exceptions=True)

    ok_count = 0
    too_many_requests_count = 0

    for response in responses:
        if isinstance(response, httpx.Response):
            if response.status_code == httpx.codes.OK:
                ok_count += 1
            elif response.status_code == httpx.codes.TOO_MANY_REQUESTS:
                too_many_requests_count += 1

    # Expect at least one 429 response if rate limiting is active
    assert too_many_requests_count >= 1, "Rate limiting did not trigger for booking endpoint"
    # Ensure successful bookings are within the limit before 429s start
    assert ok_count <= BOOKING_RATE_LIMIT
    assert ok_count + too_many_requests_count == requests_to_send


@pytest.mark.asyncio
async def test_rate_limiting_owner_registration_endpoint(client):
    # Assuming a rate limit for owner registration, e.g., 2 per minute
    REGISTRATION_RATE_LIMIT = 2
    requests_to_send = REGISTRATION_RATE_LIMIT + 2

    responses = await asyncio.gather(*[
        client.post(
            "/owner/register",
            json={
                "username": f"newowner{i}",
                "email": f"newowner{i}@example.com",
                "password": "securepassword",
                "phone": f"+" + str(2000000000 + i)
            }
        )
        for i in range(requests_to_send)
    ], return_exceptions=True)

    created_count = 0
    too_many_requests_count = 0
    conflict_count = 0 # For unique constraint violations after first successful registration

    for response in responses:
        if isinstance(response, httpx.Response):
            if response.status_code == httpx.codes.CREATED:
                created_count += 1
            elif response.status_code == httpx.codes.TOO_MANY_REQUESTS:
                too_many_requests_count += 1
            elif response.status_code == httpx.codes.CONFLICT: # Username/email already exists
                conflict_count += 1

    # Expect at least one 429 response if rate limiting is active
    assert too_many_requests_count >= 1 or (created_count + conflict_count == requests_to_send and created_count <= REGISTRATION_RATE_LIMIT), \
        "Rate limiting or proper conflict handling did not trigger for owner registration endpoint"
    # Ensure successful registrations are within the limit before 429s or conflicts
    assert created_count <= REGISTRATION_RATE_LIMIT
