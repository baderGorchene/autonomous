import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta
import json

from src import crud, models, schemas, security, notifications
from src.config import settings

# --- CRUD Tests ---
@pytest.fixture
def mock_db_session():
    return MagicMock()

@pytest.fixture
def sample_owner_data():
    return schemas.OwnerCreate(
        name="Test Owner",
        email="test@example.com",
        password="securepassword",
        business_name="Test Business",
        slug="test-business-slug"
    )

@pytest.fixture
def sample_owner_model(sample_owner_data):
    return models.Owner(
        id=1,
        name=sample_owner_data.name,
        email=sample_owner_data.email,
        hashed_password=security.get_password_hash(sample_owner_data.password),
        business_name=sample_owner_data.business_name,
        slug=sample_owner_data.slug,
        services_json="[]",
        availability_json="{}",
        phone=None
    )

def test_create_owner(mock_db_session, sample_owner_data):
    mock_db_session.add.return_value = None
    mock_db_session.commit.return_value = None
    mock_db_session.refresh.side_effect = lambda obj: obj # Simulate refresh returning the object

    owner = crud.create_owner(mock_db_session, sample_owner_data)

    assert owner.email == sample_owner_data.email
    assert security.verify_password(sample_owner_data.password, owner.hashed_password)
    mock_db_session.add.assert_called_once()
    mock_db_session.commit.assert_called_once()
    mock_db_session.refresh.assert_called_once()

def test_get_owner_by_email(mock_db_session, sample_owner_model):
    mock_db_session.query.return_value.filter.return_value.first.return_value = sample_owner_model
    owner = crud.get_owner_by_email(mock_db_session, sample_owner_model.email)
    assert owner.email == sample_owner_model.email

def test_authenticate_owner_success(mock_db_session, sample_owner_model):
    with patch('src.crud.get_owner_by_email', return_value=sample_owner_model):
        owner = crud.authenticate_owner(mock_db_session, sample_owner_model.email, "securepassword")
        assert owner.email == sample_owner_model.email

def test_authenticate_owner_wrong_password(mock_db_session, sample_owner_model):
    with patch('src.crud.get_owner_by_email', return_value=sample_owner_model):
        owner = crud.authenticate_owner(mock_db_session, sample_owner_model.email, "wrongpassword")
        assert owner is False

def test_create_booking(mock_db_session, sample_owner_model):
    booking_data = schemas.BookingCreate(
        customer_name="Jane Doe",
        customer_email="jane@example.com",
        service_name="Consultation",
        booking_time=datetime.now()
    )
    mock_db_session.add.return_value = None
    mock_db_session.commit.return_value = None
    mock_db_session.refresh.side_effect = lambda obj: obj

    booking = crud.create_booking(mock_db_session, booking_data, sample_owner_model.id)

    assert booking.customer_email == booking_data.customer_email
    assert booking.owner_id == sample_owner_model.id
    mock_db_session.add.assert_called_once()
    mock_db_session.commit.assert_called_once()
    mock_db_session.refresh.assert_called_once()

def test_update_owner_profile(mock_db_session, sample_owner_model):
    owner_update_data = schemas.OwnerProfileUpdate(
        name="Updated Name",
        business_name="Updated Business",
        phone="+1234567890"
    )
    mock_db_session.add.return_value = None
    mock_db_session.commit.return_value = None
    mock_db_session.refresh.side_effect = lambda obj: obj

    updated_owner = crud.update_owner_profile(mock_db_session, sample_owner_model, owner_update_data)

    assert updated_owner.name == owner_update_data.name
    assert updated_owner.business_name == owner_update_data.business_name
    assert updated_owner.phone == owner_update_data.phone
    mock_db_session.add.assert_called_once()
    mock_db_session.commit.assert_called_once()
    mock_db_session.refresh.assert_called_once()

# --- Security Tests ---
def test_verify_password():
    hashed_password = security.get_password_hash("testpassword")
    assert security.verify_password("testpassword", hashed_password)
    assert not security.verify_password("wrongpassword", hashed_password)

def test_create_access_token():
    to_encode = {"sub": "test@example.com"}
    token = security.create_access_token(to_encode)
    assert isinstance(token, str)
    # Decode and verify (simplified, full verification is in integration tests)
    decoded_payload = security.jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    assert decoded_payload["sub"] == "test@example.com"
    assert "exp" in decoded_payload

@patch('src.crud.get_owner_by_email')
@patch('src.security.jwt.decode')
async def test_get_current_owner_success(mock_jwt_decode, mock_get_owner_by_email, mock_db_session, sample_owner_model):
    mock_jwt_decode.return_value = {"sub": "test@example.com"}
    mock_get_owner_by_email.return_value = sample_owner_model

    owner = await security.get_current_owner("dummy_token", mock_db_session)
    assert owner.email == sample_owner_model.email

@patch('src.crud.get_owner_by_email', return_value=None)
@patch('src.security.jwt.decode', return_value={"sub": "nonexistent@example.com"})
async def test_get_current_owner_owner_not_found(mock_jwt_decode, mock_get_owner_by_email, mock_db_session):
    with pytest.raises(security.HTTPException) as exc_info:
        await security.get_current_owner("dummy_token", mock_db_session)
    assert exc_info.value.status_code == 401

# --- Notifications Tests ---
@patch('sendgrid.SendGridAPIClient')
def test_send_email_notification_success(mock_sendgrid_api_client):
    mock_sg = MagicMock()
    mock_sendgrid_api_client.return_value = mock_sg
    mock_sg.send.return_value.status_code = 202

    result = notifications.send_email_notification("recipient@example.com", "Subject", "Body")
    assert result is True
    mock_sg.send.assert_called_once()

@patch('sendgrid.SendGridAPIClient', side_effect=Exception("SendGrid Error"))
def test_send_email_notification_failure(mock_sendgrid_api_client):
    result = notifications.send_email_notification("recipient@example.com", "Subject", "Body")
    assert result is False

@patch('twilio.rest.Client')
def test_send_whatsapp_notification_success(mock_twilio_client):
    mock_client_instance = MagicMock()
    mock_twilio_client.return_value = mock_client_instance
    mock_client_instance.messages.create.return_value.sid = "SM123"

    with patch.dict(settings.model_config.model_extra, {'TWILIO_WHATSAPP_NUMBER': '+15017122661'}):
        result = notifications.send_whatsapp_notification("+1234567890", "Hello")
        assert result is True
        mock_client_instance.messages.create.assert_called_once_with(
            from_='whatsapp:+15017122661',
            body="Hello",
            to='whatsapp:+1234567890'
        )

@patch('twilio.rest.Client', side_effect=Exception("Twilio Error"))
def test_send_whatsapp_notification_failure(mock_twilio_client):
    with patch.dict(settings.model_config.model_extra, {'TWILIO_WHATSAPP_NUMBER': '+15017122661'}):
        result = notifications.send_whatsapp_notification("+1234567890", "Hello")
        assert result is False
