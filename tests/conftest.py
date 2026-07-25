import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.database import Base, get_db
from src.main import app
from src import models, crud, security, schemas
from src.config import settings
from datetime import datetime, timedelta
import pytz
import os

TEST_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    if os.path.exists("./test.db"):
        os.remove("./test.db")
    Base.metadata.create_all(bind=engine)
    yield
    engine.dispose()
    if os.path.exists("./test.db"):
        os.remove("./test.db")

@pytest.fixture(scope="function")
def db_session():
    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)

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
    app.dependency_overrides.clear()

@pytest.fixture(scope="function")
def client(db_session):
    return TestClient(app)

@pytest.fixture(scope="function")
def test_owner_data():
    return {
        "name": "Test Owner",
        "email": "test@example.com",
        "password": "testpassword",
        "business_name": "Test Business",
        "slug": "test-business",
        "phone": "+1234567890"
    }

@pytest.fixture(scope="function")
def create_test_owner(db_session, test_owner_data):
    owner_in = schemas.OwnerCreate(**test_owner_data)
    owner = crud.create_owner(db_session, owner_in)
    owner.services_json = [
        schemas.Service(name="Haircut", description="Standard haircut", price=30.0, duration_minutes=30).model_dump(),
        schemas.Service(name="Manicure", description="Nail care", price=25.0, duration_minutes=45).model_dump(),
    ]
    owner.availability_json = {
        "Monday": [{"start_time": "09:00", "end_time": "17:00"}],
        "Tuesday": [{"start_time": "09:00", "end_time": "17:00"}],
    }
    db_session.add(owner)
    db_session.commit()
    db_session.refresh(owner)
    return owner

@pytest.fixture(scope="function")
def authenticated_client(client, create_test_owner):
    owner = create_test_owner
    response = client.post(
        "/token",
        data={"username": owner.email, "password": "testpassword"},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    client.cookies["access_token"] = token
    return client
