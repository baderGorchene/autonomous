from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from src import models, schemas, crud
import pytest
from datetime import datetime, timedelta
import json
from unittest.mock import patch

@patch("src.notifications.send_email")
@patch("src.notifications.send_whatsapp_message")
def test_booking_page_not_found_error_handling(mock_send_whatsapp, mock_send_email, client: TestClient):
    response = client.get("/non-existent-slug")
    assert response.status_code == 404
    assert "Booking page not found." in response.text

@patch("src.notifications.send_email")
@patch("src.notifications.send_whatsapp_message")
def test_submit_booking_missing_fields(mock_send_whatsapp, mock_send_email, client: TestClient, test_owner: models.Owner):
    response = client.post(
        f"/{test_owner.slug}/book",
        data={
            "customer_name": "",
            "customer_email": "",
            "service_name": "",
            "booking_date": "",
            "booking_time": ""
        }
    )
    assert response.status_code == 400
    assert "Name is required." in response.text
    assert "Email is required." in response.text
    assert "Service is required." in response.text
    assert "Date is required." in response.text
    assert "Time is required." in response.text

@patch("src.notifications.send_email")
@patch("src.notifications.send_whatsapp_message")
def test_submit_booking_invalid_email(mock_send_whatsapp, mock_send_email, client: TestClient, test_owner: models.Owner):
    booking_date = (datetime.utcnow() + timedelta(days=1)).strftime("%Y-%m-%d")
    booking_time_str = (datetime.utcnow() + timedelta(days=1)).strftime("%H:%M")

    response = client.post(
        f"/{test_owner.slug}/book",
        data={
            "customer_name": "Jane Doe",
            "customer_email": "invalid-email-format",
            "service_name": "Haircut",
            "booking_date": booking_date,
            "booking_time": booking_time_str
        }
    )
    assert response.status_code == 400
    assert "Invalid email address." in response.text

@patch("src.notifications.send_email")
@patch("src.notifications.send_whatsapp_message")
def test_submit_booking_past_datetime(mock_send_whatsapp, mock_send_email, client: TestClient, test_owner: models.Owner):
    past_date = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")
    past_time = "09:00" 

    response = client.post(
        f"/{test_owner.slug}/book",
        data={
            "customer_name": "Jane Doe",
            "customer_email": "jane@example.com",
            "service_name": "Haircut",
            "booking_date": past_date,
            "booking_time": past_time
        }
    )
    assert response.status_code == 400
    assert "Booking time cannot be in the past." in response.text

@patch("src.notifications.send_email")
@patch("src.notifications.send_whatsapp_message")
def test_submit_booking_invalid_date_format(mock_send_whatsapp, mock_send_email, client: TestClient, test_owner: models.Owner):
    response = client.post(
        f"/{test_owner.slug}/book",
        data={
            "customer_name": "Jane Doe",
            "customer_email": "jane@example.com",
            "service_name": "Haircut",
            "booking_date": "invalid-date",
            "booking_time": "10:00"
        }
    )
    assert response.status_code == 400
    assert "Invalid date or time format." in response.text

def test_owner_profile_update_missing_fields(authenticated_client: TestClient, test_owner: models.Owner):
    response = authenticated_client.post(
        "/owner/profile",
        data={
            "name": "", 
            "business_name": "", 
            "phone": ""
        }
    )
    assert response.status_code == 400
    assert "Name is required." in response.text
    assert "Business name is required." in response.text

def test_owner_profile_update_invalid_phone_format(authenticated_client: TestClient, test_owner: models.Owner):
    response = authenticated_client.post(
        "/owner/profile",
        data={
            "name": "Valid Name",
            "business_name": "Valid Business",
            "phone": "not-a-phone-number"
        }
    )
    assert response.status_code == 400
    assert "Invalid phone number format." in response.text

def test_owner_signup_missing_fields(client: TestClient):
    response = client.post(
        "/owner/signup",
        data={
            "name": "",
            "email": "",
            "password": "",
            "business_name": "",
            "slug": ""
        }
    )
    assert response.status_code == 400
    assert "Name is required." in response.text
    assert "Email is required." in response.text
    assert "Password must be at least 6 characters." in response.text
    assert "Business name is required." in response.text
    assert "Slug is required." in response.text
