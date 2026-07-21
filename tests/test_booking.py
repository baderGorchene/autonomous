import pytest
import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.main import app, get_db
from src.models import Base, Owner, Booking
from src.database import DATABASE_URL

# Use a separate test database
TEST_DATABASE_URL = 'sqlite:///./test_bookslot.db'
engine = create_engine(TEST_DATABASE_URL, connect_args={'check_same_thread': False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

@pytest.fixture
def db_session():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()

@pytest.fixture
def client():
    app.dependency_overrides[get_db] = TestingSessionLocal
    with httpx.ASGITransport(app=app) as transport:
        yield httpx.AsyncClient(transport=transport, base_url='http://test')

@pytest.mark.asyncio
async def test_submit_booking_success(client, db_session):
    # Setup owner
    owner = Owner(name='Test Owner', email='test@example.com', slug='test-owner')
    db_session.add(owner)
    db_session.commit()
    
    payload = {
        "owner_id": owner.id,
        "customer_name": "John Doe",
        "customer_email": "john@example.com",
        "customer_phone": "123456789",
        "service": "Haircut",
        "datetime": "2023-12-01T10:00:00"
    }
    
    response = await client.post("/book/submit", json=payload)
    assert response.status_code == 200
    assert response.json()["status"] == "success"

@pytest.mark.asyncio
async def test_submit_booking_duplicate(client, db_session):
    owner = Owner(name='Test Owner', email='test@example.com', slug='test-owner')
    db_session.add(owner)
    db_session.commit()
    
    booking = Booking(owner_id=owner.id, customer_name='Existing', datetime='2023-12-01T10:00:00')
    db_session.add(booking)
    db_session.commit()
    
    payload = {
        "owner_id": owner.id,
        "customer_name": "New Client",
        "customer_email": "new@example.com",
        "customer_phone": "987654321",
        "service": "Haircut",
        "datetime": "2023-12-01T10:00:00"
    }
    
    response = await client.post("/book/submit", json=payload)
    assert response.status_code == 400
    assert "already booked" in response.text