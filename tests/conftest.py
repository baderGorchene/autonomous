import pytest
import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.database import Base, get_db
from src.main import app
from src.security import create_access_token, get_password_hash
from src.models import Owner, Service, RecurrenceType
from src.schemas import OwnerCreate, ServiceCreate
from datetime import datetime, time, date, timedelta


# In-memory SQLite database for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
# SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="session", autouse=True)
def setup_database():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def db_session():
    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)

    # Override the get_db dependency to use the test session
    def override_get_db():
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db

    yield session

    session.close()
    transaction.rollback()
    connection.close()
    app.dependency_overrides = {}


@pytest.fixture(scope="function")
async def client(db_session):
    async with httpx.AsyncClient(app=app, base_url="http://test") as client:
        yield client


@pytest.fixture(scope="function")
def test_owner(db_session):
    hashed_password = get_password_hash("testpassword")
    owner_data = OwnerCreate(
        username="testowner",
        email="test@example.com",
        password="testpassword",
        phone="+15551234567"
    )
    owner = Owner(**owner_data.model_dump(exclude={'password'}), hashed_password=hashed_password)
    db_session.add(owner)
    db_session.commit()
    db_session.refresh(owner)
    return owner


@pytest.fixture(scope="function")
def test_owner2(db_session):
    hashed_password = get_password_hash("testpassword2")
    owner_data = OwnerCreate(
        username="testowner2",
        email="test2@example.com",
        password="testpassword2",
        phone="+15551234568"
    )
    owner = Owner(**owner_data.model_dump(exclude={'password'}), hashed_password=hashed_password)
    db_session.add(owner)
    db_session.commit()
    db_session.refresh(owner)
    return owner


@pytest.fixture(scope="function")
def test_owner_token(test_owner):
    access_token_expires = timedelta(minutes=30)
    token = create_access_token(
        data={"sub": test_owner.username},
        expires_delta=access_token_expires
    )
    return token


@pytest.fixture(scope="function")
def test_service(db_session, test_owner):
    service_data = ServiceCreate(
        name="Consultation",
        description="A 30-minute consultation session.",
        duration_minutes=30,
        price=50.00
    )
    service = Service(**service_data.model_dump(), owner_id=test_owner.id)
    db_session.add(service)
    db_session.commit()
    db_session.refresh(service)
    return service


@pytest.fixture(scope="function")
def test_availability(db_session, test_owner, test_service):
    availability = models.Availability(
        owner_id=test_owner.id,
        service_id=test_service.id,
        date=None, # Recurring
        recurrence_type=RecurrenceType.DAILY,
        start_time=time(9, 0),
        end_time=time(17, 0)
    )
    db_session.add(availability)
    db_session.commit()
    db_session.refresh(availability)
    return availability


@pytest.fixture(scope="function")
def test_booking(db_session, test_owner, test_service, test_availability):
    booking = models.Booking(
        owner_id=test_owner.id,
        service_id=test_service.id,
        customer_name="Jane Doe",
        customer_email="jane@example.com",
        customer_phone="+15559876543",
        date=date.today() + timedelta(days=1),
        time=time(10, 0),
        is_recurring=False
    )
    db_session.add(booking)
    db_session.commit()
    db_session.refresh(booking)
    return booking
