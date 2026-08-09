from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from datetime import date, time, timedelta
import pytest
from unittest.mock import patch
from freezegun import freeze_time

from src.main import app
from src import models, schemas, security
from src.config import settings
from src.database import Base, engine

# Setup for tests
@pytest.fixture(scope="module")
def client():
    # Use a test database
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as c:
        yield c
    Base.metadata.drop_all(bind=engine)

@pytest.fixture(scope="function")
def db_session():
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)

    # Override the get_db dependency to use this session
    def override_get_db():
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[security.get_db] = override_get_db

    yield session

    session.close()
    transaction.rollback()
    connection.close()
    app.dependency_overrides.clear()

@pytest.fixture(scope="function")
def test_owner(db_session: Session):
    owner_data = {
        "email": "owner@example.com",
        "password": "testpassword",
        "username": "testowner",
        "phone": "+1234567890"
    }
    owner = models.Owner(
        email=owner_data["email"],
        hashed_password=security.get_password_hash(owner_data["password"]),
        username=owner_data["username"],
        phone=owner_data["phone"]
    )
    db_session.add(owner)
    db_session.commit()
    db_session.refresh(owner)
    return owner

@pytest.fixture(scope="function")
def test_service(db_session: Session, test_owner: models.Owner):
    service_data = schemas.ServiceCreate(
        name="Haircut",
        description="Professional haircut",
        duration_minutes=60,
        price=50.0
    )
    service = models.Service(**service_data.dict(), owner_id=test_owner.id)
    db_session.add(service)
    db_session.commit()
    db_session.refresh(service)
    return service

@pytest.fixture(scope="function")
def owner_token(client: TestClient, test_owner: models.Owner):
    response = client.post(
        "/owner/token",
        data={
            "username": test_owner.email,
            "password": "testpassword"
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    assert response.status_code == 200
    return response.json()["access_token"]


# --- Test Cases for Recurring Availabilities ---

def test_create_daily_recurring_availability(client: TestClient, db_session: Session, test_owner: models.Owner, owner_token: str):
    with freeze_time("2023-01-01"):
        availability_data = {
            "service_id": None, # All services
            "start_time": "09:00",
            "end_time": "17:00",
            "date": None, # Recurring
            "recurrence_type": "DAILY",
            "recurrence_value": None,
            "recurrence_start_date": "2023-01-01",
            "recurrence_end_date": "2023-01-31"
        }
        response = client.post(
            f"/owner/availability",
            json=availability_data,
            headers={"Authorization": f"Bearer {owner_token}"}
        )
        assert response.status_code == 200
        created_avail = response.json()
        assert created_avail["recurrence_type"] == "DAILY"
        assert created_avail["recurrence_start_date"] == "2023-01-01"
        assert created_avail["recurrence_end_date"] == "2023-01-31"

        # Verify it's in the DB
        db_avail = db_session.query(models.Availability).filter_by(id=created_avail["id"]).first()
        assert db_avail is not None
        assert db_avail.recurrence_type == models.RecurrenceType.DAILY


def test_create_weekly_recurring_availability(client: TestClient, db_session: Session, test_owner: models.Owner, owner_token: str):
    with freeze_time("2023-01-01"):
        availability_data = {
            "service_id": None,
            "start_time": "10:00",
            "end_time": "18:00",
            "date": None,
            "recurrence_type": "WEEKLY",
            "recurrence_value": "MON,WED,FRI",
            "recurrence_start_date": "2023-01-01",
            "recurrence_end_date": "2023-01-31"
        }
        response = client.post(
            f"/owner/availability",
            json=availability_data,
            headers={"Authorization": f"Bearer {owner_token}"}
        )
        assert response.status_code == 200
        created_avail = response.json()
        assert created_avail["recurrence_type"] == "WEEKLY"
        assert created_avail["recurrence_value"] == "MON,WED,FRI"


def test_create_monthly_recurring_availability(client: TestClient, db_session: Session, test_owner: models.Owner, owner_token: str):
    with freeze_time("2023-01-01"):
        availability_data = {
            "service_id": None,
            "start_time": "11:00",
            "end_time": "19:00",
            "date": None,
            "recurrence_type": "MONTHLY",
            "recurrence_value": "15", # 15th of every month
            "recurrence_start_date": "2023-01-01",
            "recurrence_end_date": "2023-06-30"
        }
        response = client.post(
            f"/owner/availability",
            json=availability_data,
            headers={"Authorization": f"Bearer {owner_token}"}
        )
        assert response.status_code == 200
        created_avail = response.json()
        assert created_avail["recurrence_type"] == "MONTHLY"
        assert created_avail["recurrence_value"] == "15"


# --- Test Cases for Public Booking Page Slot Generation with Recurring Availabilities ---

def test_get_available_slots_with_daily_recurrence(client: TestClient, db_session: Session, test_owner: models.Owner, test_service: models.Service):
    # Create a daily recurring availability
    with freeze_time("2023-01-01"):
        availability = models.Availability(
            owner_id=test_owner.id,
            service_id=test_service.id,
            start_time=time(9, 0),
            end_time=time(17, 0),
            recurrence_type=models.RecurrenceType.DAILY,
            recurrence_start_date=date(2023, 1, 1),
            recurrence_end_date=date(2023, 1, 31)
        )
        db_session.add(availability)
        db_session.commit()

        # Check a date within the recurrence range
        target_date = date(2023, 1, 5) # A Thursday
        response = client.get(f"/book/{test_owner.username}/slots", params={
            "service_id": test_service.id,
            "date": target_date.isoformat()
        })
        assert response.status_code == 200
        slots = response.json()
        assert "09:00" in slots
        assert "16:00" in slots # Last possible slot for 60-min service ending at 17:00
        assert len(slots) == 8 # (17-9) hours = 8 hours = 8 slots of 60 mins

        # Check a date outside the recurrence range
        target_date_out_of_range = date(2023, 2, 1)
        response = client.get(f"/book/{test_owner.username}/slots", params={
            "service_id": test_service.id,
            "date": target_date_out_of_range.isoformat()
        })
        assert response.status_code == 200
        slots = response.json()
        assert len(slots) == 0

def test_get_available_slots_with_weekly_recurrence(client: TestClient, db_session: Session, test_owner: models.Owner, test_service: models.Service):
    # Create a weekly recurring availability for MON, WED, FRI
    with freeze_time("2023-01-01"):
        availability = models.Availability(
            owner_id=test_owner.id,
            service_id=test_service.id,
            start_time=time(10, 0),
            end_time=time(14, 0),
            recurrence_type=models.RecurrenceType.WEEKLY,
            recurrence_value="MON,WED,FRI",
            recurrence_start_date=date(2023, 1, 1),
            recurrence_end_date=date(2023, 1, 31)
        )
        db_session.add(availability)
        db_session.commit()

        # Check a Monday (within recurrence value)
        target_date_mon = date(2023, 1, 2) # Monday
        response = client.get(f"/book/{test_owner.username}/slots", params={
            "service_id": test_service.id,
            "date": target_date_mon.isoformat()
        })
        assert response.status_code == 200
        slots_mon = response.json()
        assert "10:00" in slots_mon
        assert "13:00" in slots_mon # Last possible slot for 60-min service ending at 14:00
        assert len(slots_mon) == 4 # (14-10) hours = 4 hours = 4 slots

        # Check a Tuesday (not in recurrence value)
        target_date_tue = date(2023, 1, 3) # Tuesday
        response = client.get(f"/book/{test_owner.username}/slots", params={
            "service_id": test_service.id,
            "date": target_date_tue.isoformat()
        })
        assert response.status_code == 200
        slots_tue = response.json()
        assert len(slots_tue) == 0

def test_get_available_slots_with_monthly_recurrence(client: TestClient, db_session: Session, test_owner: models.Owner, test_service: models.Service):
    # Create a monthly recurring availability for the 15th of the month
    with freeze_time("2023-01-01"):
        availability = models.Availability(
            owner_id=test_owner.id,
            service_id=test_service.id,
            start_time=time(9, 0),
            end_time=time(12, 0),
            recurrence_type=models.RecurrenceType.MONTHLY,
            recurrence_value="15",
            recurrence_start_date=date(2023, 1, 1),
            recurrence_end_date=date(2023, 3, 31)
        )
        db_session.add(availability)
        db_session.commit()

        # Check on the 15th of January
        target_date_15_jan = date(2023, 1, 15)
        response = client.get(f"/book/{test_owner.username}/slots", params={
            "service_id": test_service.id,
            "date": target_date_15_jan.isoformat()
        })
        assert response.status_code == 200
        slots_15_jan = response.json()
        assert "09:00" in slots_15_jan
        assert "11:00" in slots_15_jan # Last possible slot for 60-min service ending at 12:00
        assert len(slots_15_jan) == 3 # (12-9) hours = 3 hours = 3 slots

        # Check on the 16th of January (not the 15th)
        target_date_16_jan = date(2023, 1, 16)
        response = client.get(f"/book/{test_owner.username}/slots", params={
            "service_id": test_service.id,
            "date": target_date_16_jan.isoformat()
        })
        assert response.status_code == 200
        slots_16_jan = response.json()
        assert len(slots_16_jan) == 0


# --- Test Cases for Submitting Recurring Bookings ---

@patch("src.notifications.send_email_notification")
@patch("src.notifications.send_whatsapp_notification")
def test_submit_daily_recurring_booking(mock_send_whatsapp, mock_send_email, client: TestClient, db_session: Session, test_owner: models.Owner, test_service: models.Service):
    with freeze_time("2023-01-01"):
        # Setup daily availability
        availability = models.Availability(
            owner_id=test_owner.id,
            service_id=test_service.id,
            start_time=time(10, 0),
            end_time=time(12, 0),
            recurrence_type=models.RecurrenceType.DAILY,
            recurrence_start_date=date(2023, 1, 1),
            recurrence_end_date=date(2023, 1, 3)
        )
        db_session.add(availability)
        db_session.commit()

        booking_data = {
            "service_id": test_service.id,
            "customer_name": "Jane Doe",
            "customer_email": "jane@example.com",
            "customer_phone": "+1987654321",
            "date": "2023-01-01",
            "time": "10:00",
            "recurrence_type": "DAILY",
            "recurrence_value": None,
            "recurrence_end_date": "2023-01-03"
        }

        response = client.post(
            f"/book/{test_owner.username}",
            json=booking_data
        )
        assert response.status_code == 200
        confirmation = response.json()
        assert "Booking(s) confirmed" in confirmation["message"]

        # Verify 3 bookings were created (Jan 1, 2, 3)
        bookings = db_session.query(models.Booking).filter(
            models.Booking.owner_id == test_owner.id,
            models.Booking.service_id == test_service.id,
            models.Booking.customer_email == "jane@example.com"
        ).order_by(models.Booking.date).all()

        assert len(bookings) == 3
        assert bookings[0].date == date(2023, 1, 1)
        assert bookings[1].date == date(2023, 1, 2)
        assert bookings[2].date == date(2023, 1, 3)
        
        # Verify notifications were sent for each booking
        assert mock_send_email.call_count == 3 * 2 # 3 bookings * (owner + customer)
        assert mock_send_whatsapp.call_count == 3 * 2 # 3 bookings * (owner + customer)


@patch("src.notifications.send_email_notification")
@patch("src.notifications.send_whatsapp_notification")
def test_submit_weekly_recurring_booking(mock_send_whatsapp, mock_send_email, client: TestClient, db_session: Session, test_owner: models.Owner, test_service: models.Service):
    with freeze_time("2023-01-01"):
        # Setup weekly availability for MON, WED
        availability = models.Availability(
            owner_id=test_owner.id,
            service_id=test_service.id,
            start_time=time(10, 0),
            end_time=time(12, 0),
            recurrence_type=models.RecurrenceType.WEEKLY,
            recurrence_value="MON,WED",
            recurrence_start_date=date(2023, 1, 1),
            recurrence_end_date=date(2023, 1, 10) # Covers two Mondays and two Wednesdays
        )
        db_session.add(availability)
        db_session.commit()

        booking_data = {
            "service_id": test_service.id,
            "customer_name": "John Smith",
            "customer_email": "john@example.com",
            "customer_phone": "+1122334455",
            "date": "2023-01-02", # Start on a Monday
            "time": "10:00",
            "recurrence_type": "WEEKLY",
            "recurrence_value": "MON,WED",
            "recurrence_end_date": "2023-01-10"
        }

        response = client.post(
            f"/book/{test_owner.username}",
            json=booking_data
        )
        assert response.status_code == 200
        confirmation = response.json()
        assert "Booking(s) confirmed" in confirmation["message"]

        # Verify bookings were created for Jan 2 (Mon), Jan 4 (Wed), Jan 9 (Mon), Jan 11 (Wed) - wait, end_date is Jan 10
        # So: Jan 2 (Mon), Jan 4 (Wed), Jan 9 (Mon)
        bookings = db_session.query(models.Booking).filter(
            models.Booking.owner_id == test_owner.id,
            models.Booking.service_id == test_service.id,
            models.Booking.customer_email == "john@example.com"
        ).order_by(models.Booking.date).all()
        
        assert len(bookings) == 3
        assert bookings[0].date == date(2023, 1, 2) # Mon
        assert bookings[1].date == date(2023, 1, 4) # Wed
        assert bookings[2].date == date(2023, 1, 9) # Mon

        assert mock_send_email.call_count == 3 * 2
        assert mock_send_whatsapp.call_count == 3 * 2


@patch("src.notifications.send_email_notification")
@patch("src.notifications.send_whatsapp_notification")
def test_submit_monthly_recurring_booking(mock_send_whatsapp, mock_send_email, client: TestClient, db_session: Session, test_owner: models.Owner, test_service: models.Service):
    with freeze_time("2023-01-01"):
        # Setup monthly availability for the 15th
        availability = models.Availability(
            owner_id=test_owner.id,
            service_id=test_service.id,
            start_time=time(10, 0),
            end_time=time(12, 0),
            recurrence_type=models.RecurrenceType.MONTHLY,
            recurrence_value="15",
            recurrence_start_date=date(2023, 1, 1),
            recurrence_end_date=date(2023, 3, 31)
        )
        db_session.add(availability)
        db_session.commit()

        booking_data = {
            "service_id": test_service.id,
            "customer_name": "Alice Brown",
            "customer_email": "alice@example.com",
            "customer_phone": "+1555123456",
            "date": "2023-01-15", # Start on the 15th
            "time": "10:00",
            "recurrence_type": "MONTHLY",
            "recurrence_value": "15",
            "recurrence_end_date": "2023-03-31"
        }

        response = client.post(
            f"/book/{test_owner.username}",
            json=booking_data
        )
        assert response.status_code == 200
        confirmation = response.json()
        assert "Booking(s) confirmed" in confirmation["message"]

        # Verify bookings were created for Jan 15, Feb 15, Mar 15
        bookings = db_session.query(models.Booking).filter(
            models.Booking.owner_id == test_owner.id,
            models.Booking.service_id == test_service.id,
            models.Booking.customer_email == "alice@example.com"
        ).order_by(models.Booking.date).all()

        assert len(bookings) == 3
        assert bookings[0].date == date(2023, 1, 15)
        assert bookings[1].date == date(2023, 2, 15)
        assert bookings[2].date == date(2023, 3, 15)

        assert mock_send_email.call_count == 3 * 2
        assert mock_send_whatsapp.call_count == 3 * 2


# --- Test Cases for Dashboard Display of Recurring Bookings ---

def test_dashboard_displays_recurring_bookings(client: TestClient, db_session: Session, test_owner: models.Owner, test_service: models.Service, owner_token: str):
    with freeze_time("2023-01-01"):
        # Setup daily availability
        availability = models.Availability(
            owner_id=test_owner.id,
            service_id=test_service.id,
            start_time=time(10, 0),
            end_time=time(12, 0),
            recurrence_type=models.RecurrenceType.DAILY,
            recurrence_start_date=date(2023, 1, 1),
            recurrence_end_date=date(2023, 1, 3)
        )
        db_session.add(availability)
        db_session.commit()

        # Create a recurring booking
        booking_data = {
            "service_id": test_service.id,
            "customer_name": "Dashboard User",
            "customer_email": "dashboard@example.com",
            "customer_phone": "+1112223333",
            "date": "2023-01-01",
            "time": "10:00",
            "recurrence_type": "DAILY",
            "recurrence_value": None,
            "recurrence_end_date": "2023-01-03"
        }
        client.post(f"/book/{test_owner.username}", json=booking_data)

        # Access dashboard
        response = client.get(
            "/owner/dashboard",
            headers={"Authorization": f"Bearer {owner_token}"}
        )
        assert response.status_code == 200
        dashboard_data = response.json()
        
        # Verify individual bookings are listed
        upcoming_bookings = dashboard_data["upcoming_bookings"]
        assert len(upcoming_bookings) == 3

        # Check details of one booking
        booking_dates = [b["date"] for b in upcoming_bookings]
        assert "2023-01-01" in booking_dates
        assert "2023-01-02" in booking_dates
        assert "2023-01-03" in booking_dates

        first_booking = next(b for b in upcoming_bookings if b["date"] == "2023-01-01")
        assert first_booking["customer_name"] == "Dashboard User"
        assert first_booking["service_name"] == test_service.name
        assert first_booking["time"] == "10:00:00"

