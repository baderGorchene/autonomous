import pytest
import httpx
from datetime import datetime, time, timedelta


@pytest.mark.asyncio
async def test_xss_owner_profile_update(client, db_session, test_owner, test_owner_token):
    # Attempt XSS injection in owner name
    xss_payload = "<script>alert('XSS-OwnerName')</script>"
    response = await client.put(
        f"/owner/profile/{test_owner.id}",
        headers={
            "Authorization": f"Bearer {test_owner_token}"
        },
        json={
            "name": xss_payload,
            "email": test_owner.email,
            "phone": test_owner.phone
        }
    )
    assert response.status_code == httpx.codes.OK

    # Retrieve the profile and check if the payload is escaped
    profile_response = await client.get(
        f"/owner/profile/{test_owner.id}",
        headers={
            "Authorization": f"Bearer {test_owner_token}"
        }
    )
    assert profile_response.status_code == httpx.codes.OK
    profile_data = profile_response.json()
    assert profile_data["name"] == xss_payload  # Stored literally in API, rendering layer should escape

    # Test rendering on dashboard (assuming dashboard pulls this data)
    dashboard_response = await client.get(
        "/owner/dashboard",
        headers={
            "Authorization": f"Bearer {test_owner_token}"
        }
    )
    assert dashboard_response.status_code == httpx.codes.OK
    # Check if the XSS payload is escaped in the HTML content
    assert "&lt;script&gt;alert('XSS-OwnerName')&lt;/script&gt;" in dashboard_response.text
    assert "<script>alert('XSS-OwnerName')</script>" not in dashboard_response.text


@pytest.mark.asyncio
async def test_xss_service_description(client, db_session, test_owner, test_owner_token):
    # Attempt XSS injection in service description
    xss_payload = "<img src=x onerror=alert('XSS-ServiceDesc')>"
    response = await client.post(
        "/owner/services",
        headers={
            "Authorization": f"Bearer {test_owner_token}"
        },
        json={
            "name": "XSS Service",
            "description": xss_payload,
            "duration_minutes": 60,
            "price": 100.00
        }
    )
    assert response.status_code == httpx.codes.CREATED
    service_data = response.json()
    assert service_data["description"] == xss_payload # Stored literally in API

    # Test rendering on public booking page
    booking_page_response = await client.get(f"/book/{test_owner.username}/{service_data['id']}")
    assert booking_page_response.status_code == httpx.codes.OK
    # Check if the XSS payload is escaped in the HTML content
    assert "&lt;img src=x onerror=alert('XSS-ServiceDesc')&gt;" in booking_page_response.text
    assert "<img src=x onerror=alert('XSS-ServiceDesc')>" not in booking_page_response.text


@pytest.mark.asyncio
async def test_xss_customer_review_submission(client, db_session, test_owner, test_service, test_availability):
    # Simulate a customer booking to get a booking ID for review
    booking_date = datetime.now().date() + timedelta(days=1)
    booking_time = time(10, 0)
    booking_response = await client.post(
        f"/book/{test_owner.username}/{test_service.id}",
        json={
            "customer_name": "Reviewer",
            "customer_email": "reviewer@example.com",
            "customer_phone": "+1234567890",
            "date": booking_date.isoformat(),
            "time": booking_time.isoformat(),
            "is_recurring": False
        }
    )
    assert booking_response.status_code == httpx.codes.OK
    booking_data = booking_response.json()
    booking_id = booking_data["id"]

    # Attempt XSS injection in review text
    xss_payload = "<marquee>I am a moving text</marquee><script>document.cookie='hacked'</script>"
    review_response = await client.post(
        f"/reviews",
        json={
            "booking_id": booking_id,
            "rating": 5,
            "comment": xss_payload
        }
    )
    assert review_response.status_code == httpx.codes.CREATED
    review_data = review_response.json()
    assert review_data["comment"] == xss_payload # Stored literally in API

    # Test rendering on public booking page (where reviews might be displayed)
    public_page_response = await client.get(f"/book/{test_owner.username}/{test_service.id}")
    assert public_page_response.status_code == httpx.codes.OK
    # Check if the XSS payload is escaped in the HTML content
    assert "&lt;marquee&gt;I am a moving text&lt;/marquee&gt;&lt;script&gt;document.cookie='hacked'" in public_page_response.text
    assert "<marquee>I am a moving text</marquee><script>document.cookie='hacked'</script>" not in public_page_response.text
