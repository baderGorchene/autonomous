import pytest
import httpx
from src.models import RecurrenceType
from datetime import time, date, timedelta


@pytest.mark.asyncio
async def test_unauthorized_owner_access_other_owner_profile(client, test_owner, test_owner2, test_owner_token):
    # test_owner tries to access test_owner2's profile
    response = await client.get(
        f"/owner/profile/{test_owner2.id}",
        headers={
            "Authorization": f"Bearer {test_owner_token}"
        }
    )
    assert response.status_code == httpx.codes.FORBIDDEN
    assert response.json() == {"detail": "Not authorized to access this resource"}


@pytest.mark.asyncio
async def test_unauthorized_owner_update_other_owner_profile(client, test_owner, test_owner2, test_owner_token):
    # test_owner tries to update test_owner2's profile
    response = await client.put(
        f"/owner/profile/{test_owner2.id}",
        headers={
            "Authorization": f"Bearer {test_owner_token}"
        },
        json={
            "name": "New Name for Owner2",
            "email": test_owner2.email,
            "phone": test_owner2.phone
        }
    )
    assert response.status_code == httpx.codes.FORBIDDEN
    assert response.json() == {"detail": "Not authorized to access this resource"}


@pytest.mark.asyncio
async def test_unauthorized_owner_access_other_owner_service(client, db_session, test_owner, test_owner2, test_owner_token):
    # Create a service for test_owner2
    service_for_owner2 = await client.post(
        "/owner/services",
        headers={
            "Authorization": f"Bearer {test_owner_token}"
        },
        json={
            "name": "Owner2 Service",
            "description": "Desc",
            "duration_minutes": 30,
            "price": 25.00
        }
    )
    service_for_owner2_id = service_for_owner2.json()["id"]

    # test_owner tries to access test_owner2's service (should be forbidden if endpoint verifies ownership)
    # NOTE: The service endpoints currently require the service to belong to the authenticated owner.
    # This test case implicitly checks that.
    response = await client.get(
        f"/owner/services/{service_for_owner2_id}",
        headers={
            "Authorization": f"Bearer {test_owner_token}"
        }
    )
    assert response.status_code == httpx.codes.FORBIDDEN
    assert response.json() == {"detail": "Not authorized to access this resource"}


@pytest.mark.asyncio
async def test_unauthorized_owner_update_other_owner_service(client, db_session, test_owner, test_owner2, test_owner_token):
    # Create a service for test_owner2
    service_for_owner2 = await client.post(
        "/owner/services",
        headers={
            "Authorization": f"Bearer {test_owner_token}"
        },
        json={
            "name": "Owner2 Service",
            "description": "Desc",
            "duration_minutes": 30,
            "price": 25.00
        }
    )
    service_for_owner2_id = service_for_owner2.json()["id"]

    # test_owner tries to update test_owner2's service
    response = await client.put(
        f"/owner/services/{service_for_owner2_id}",
        headers={
            "Authorization": f"Bearer {test_owner_token}"
        },
        json={
            "name": "Updated Service Name",
            "description": "Updated Description",
            "duration_minutes": 45,
            "price": 30.00
        }
    )
    assert response.status_code == httpx.codes.FORBIDDEN
    assert response.json() == {"detail": "Not authorized to access this resource"}


@pytest.mark.asyncio
async def test_unauthorized_owner_access_other_owner_booking(client, db_session, test_owner, test_owner2, test_owner_token, test_service, test_availability):
    # Create a booking for test_owner2 (using test_owner2's token to create it)
    owner2_token_response = await client.post("/token", data={"username": test_owner2.username, "password": "testpassword2"})
    owner2_token = owner2_token_response.json()["access_token"]

    service_for_owner2 = await client.post(
        "/owner/services",
        headers={
            "Authorization": f"Bearer {owner2_token}"
        },
        json={
            "name": "Owner2 Service",
            "description": "Desc",
            "duration_minutes": 30,
            "price": 25.00
        }
    )
    service_for_owner2_id = service_for_owner2.json()["id"]

    booking_date = date.today() + timedelta(days=2)
    booking_time = time(11, 0)
    booking_response = await client.post(
        f"/book/{test_owner2.username}/{service_for_owner2_id}",
        json={
            "customer_name": "Customer For Owner2",
            "customer_email": "customer2@example.com",
            "customer_phone": "+1234567891",
            "date": booking_date.isoformat(),
            "time": booking_time.isoformat(),
            "is_recurring": False
        }
    )
    assert booking_response.status_code == httpx.codes.OK
    booking_id_for_owner2 = booking_response.json()["id"]

    # test_owner tries to access test_owner2's booking
    response = await client.get(
        f"/owner/bookings/{booking_id_for_owner2}",
        headers={
            "Authorization": f"Bearer {test_owner_token}"
        }
    )
    assert response.status_code == httpx.codes.FORBIDDEN
    assert response.json() == {"detail": "Not authorized to access this resource"}
