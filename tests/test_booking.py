from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from src import models, schemas, crud
import pytest
from datetime import datetime, timedelta
import json
from unittest.mock import patch

@patch("src.notifications.send_email")
@patch("src.notifications.send_whatsapp_message")
def test_public_booking_page(mock_send_whatsapp, mock_send_email, client: TestClient, test_owner: models.Owner):
    response = client.get(f"/{test_owner.slug}")
    assert response.status_code == 200
    assert f"{test_owner.business_name} - Book an Appointment" in response.text
    assert f"Book an Appointment with {test_owner.name}" in response.text
    assert "Haircut (30 min)" in response.text 

@patch("src.notifications.send_email")
@patch("src.notifications.send_whatsapp_message")
def test_public_booking_page_not_found(mock_send_whatsapp, mock_send_email, client: TestClient):
    response = client.get("/non-existent-slug")
    assert response.status_code == 404
    assert "Booking page not found." in response.text

@patch("src.notifications.send_email")
@patch("src.notifications.send_whatsapp_message")
def test_submit_booking_success(mock_send_whatsapp, mock_send_email, client: TestClient, db: Session, test_owner: models.Owner):
    booking_time = (datetime.utcnow() + timedelta(days=1)).strftime("%Y-%m-%d %H:%M")
    booking_date = (datetime.utcnow() + timedelta(days=1)).strftime("%Y-%m-%d")
    booking_time_str = (datetime.utcnow() + timedelta(days=1)).strftime("%H:%M")

    response = client.post(
        f"/{test_owner.slug}/book",
        data={
            "customer_name": "John Doe",
            "customer_email": "john.doe@example.com",
            "customer_phone": "+11234567890",
            "service_name": "Haircut",
            "booking_date": booking_date,
            "booking_time": booking_time_str
        }
    )
    assert response.status_code == 200
    assert "Thank You for Your Booking!" in response.text
    assert "A confirmation email has been sent to john.doe@example.com." in response.text

    booking = db.query(models.Booking).filter_by(customer_email="john.doe@example.com").first()
    assert booking is not None
    assert booking.owner_id == test_owner.id
    assert booking.service_name == "Haircut"
    assert booking.status == "pending"

    assert mock_send_email.call_count == 2 
    assert mock_send_whatsapp.call_count == 1 

@patch("src.notifications.send_email")
@patch("src.notifications.send_whatsapp_message")
def test_submit_booking_validation_error(mock_send_whatsapp, mock_send_email, client: TestClient, test_owner: models.Owner):
    response = client.post(
        f"/{test_owner.slug}/book",
        data={
            "customer_name": "", 
            "customer_email": "invalid-email", 
            "service_name": "Haircut",
            "booking_date": "2023-01-01", 
            "booking_time": "09:00"
        }
    )
    assert response.status_code == 400
    assert "Name is required." in response.text
    assert "Invalid email address." in response.text
    assert "Booking time cannot be in the past." in response.text
    assert "Book an Appointment with Test Owner" in response.text 

    mock_send_email.assert_not_called()
    mock_send_whatsapp.assert_not_called()

@patch("src.notifications.send_email")
@patch("src.notifications.send_whatsapp_message")
def test_submit_booking_past_time_error(mock_send_whatsapp, mock_send_email, client: TestClient, test_owner: models.Owner):
    past_date = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")
    current_time = datetime.now().strftime("%H:%M") 
    response = client.post(
        f"/{test_owner.slug}/book",
        data={
            "customer_name": "Test Past",
            "customer_email": "past@example.com",
            "service_name": "Haircut",
            "booking_date": past_date,
            "booking_time": current_time
        }
    )
    assert response.status_code == 400
    assert "Booking time cannot be in the past." in response.text
