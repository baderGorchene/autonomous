import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from datetime import date, time, timedelta
from src.main import app
from src.config import settings
from src.database import Base, get_db
from src import models, schemas, security
from src.availability_utils import get_available_slots_for_day
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
@pytest.fixture(name="db_session")
def db_session_fixture():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
@pytest.fixture(name="client")
def client_fixture(db_session: Session):
    def override_get_db():
        yield db_session
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
def create_owner_and_service(db: Session):
    owner_data = schemas.OwnerCreate(
        name="Test Owner",
        email="owner@example.com",
        phone="+1234567890",
        password="testpassword"
    )
    hashed_password = security.get_password_hash(owner_data.password)
    db_owner = models.Owner(
        name=owner_data.name,
        email=owner_data.email,
        phone=owner_data.phone,
        hashed_password=hashed_password
    )
    db.add(db_owner)
    db.commit()
    db.refresh(db_owner)
    service_data = schemas.ServiceCreate(
        name="Recurring Service",
        description="A service with recurring availability",
        duration_minutes=60,
        price=50.0
    )
    db_service = models.Service(**service_data.model_dump(), owner_id=db_owner.id)
    db.add(db_service)
    db.commit()
    db.refresh(db_service)
    return db_owner, db_service
def get_owner_token(client: TestClient, owner_email: str = "owner@example.com", owner_password: str = "testpassword"):
    response = client.post(
        "/token",
        data={"username": owner_email, "password": owner_password}
    )
    assert response.status_code == 200
    return response.json()["access_token"]
def test_create_daily_recurring_availability(client: TestClient, db_session: Session):
    owner, service = create_owner_and_service(db_session)
    token = get_owner_token(client)
    start_date = date.today() + timedelta(days=1)
    end_date = start_date + timedelta(days=7)
    availability_data = schemas.AvailabilityCreate(
        service_id=service.id,
        start_time=time(9, 0),
        end_time=time(17, 0),
        recurrence_type=models.RecurrenceType.DAILY,
        recurrence_start_date=start_date,
        recurrence_end_date=end_date
    )
    response = client.post(
        "/owner/availabilities/",
        json=availability_data.model_dump(),
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    assert response.json()["recurrence_type"] == models.RecurrenceType.DAILY.value
    for i in range(3):
        target_date = start_date + timedelta(days=i)
        available_slots = get_available_slots_for_day(db_session, owner.id, service.id, target_date, service.duration_minutes)
        assert len(available_slots) > 0
        assert time(9, 0) in available_slots
        assert time(16, 0) in available_slots
def test_book_recurring_slot(client: TestClient, db_session: Session):
    owner, service = create_owner_and_service(db_session)
    token = get_owner_token(client)
    start_date = date.today() + timedelta(days=2)
    end_date = start_date + timedelta(days=7)
    availability_data = schemas.AvailabilityCreate(
        service_id=service.id,
        start_time=time(10, 0),
        end_time=time(12, 0),
        recurrence_type=models.RecurrenceType.DAILY,
        recurrence_start_date=start_date,
        recurrence_end_date=end_date
    )
    client.post(
        "/owner/availabilities/",
        json=availability_data.model_dump(),
        headers={"Authorization": f"Bearer {token}"}
    )
    booking_date = start_date
    booking_time = time(10, 0)
    customer_data = schemas.CustomerCreate(
        name="John Doe",
        email="john@example.com",
        phone="+1122334455"
    )
    booking_data = schemas.BookingCreate(
        service_id=service.id,
        date=booking_date,
        time=booking_time,
        customer_name=customer_data.name,
        customer_email=customer_data.email,
        customer_phone=customer_data.phone
    )
    response = client.post(
        f"/book/{owner.id}",
        json=booking_data.model_dump()
    )
    assert response.status_code == 200
    assert response.json()["customer_name"] == "John Doe"
    assert response.json()["date"] == booking_date.isoformat()
    assert response.json()["time"] == booking_time.isoformat(timespec='minutes')
    available_slots_day1 = get_available_slots_for_day(db_session, owner.id, service.id, booking_date, service.duration_minutes)
    assert booking_time not in available_slots_day1
    next_recurring_day = booking_date + timedelta(days=1)
    available_slots_day2 = get_available_slots_for_day(db_session, owner.id, service.id, next_recurring_day, service.duration_minutes)
    assert booking_time in available_slots_day2