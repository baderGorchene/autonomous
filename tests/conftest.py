import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.database import Base, get_db
from src.main import app
from src import models, security
import os
import json
from datetime import datetime, timedelta

SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="session")
def db_engine():
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)

@pytest.fixture(scope="function")
def db(db_engine):
    connection = db_engine.connect()
    transaction = connection.begin()
    db = TestingSessionLocal(bind=connection)

    yield db

    db.close()
    transaction.rollback()
    connection.close()

@pytest.fixture(scope="function")
def client(db):
    def override_get_db():
        try:
            yield db
        finally:
            db.close()
    
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides = {} 

@pytest.fixture(scope="function")
def test_owner(db):
    hashed_password = security.get_password_hash("testpassword")
    owner_data = models.Owner(
        name="Test Owner",
        email="test@example.com",
        hashed_password=hashed_password,
        business_name="Test Business",
        slug="test-business",
        phone="+1234567890",
        services_json=json.dumps([{"name": "Haircut", "duration_minutes": 30, "price": 25.0}]),
        availability_json=json.dumps({
            "monday": [{"start_time": "09:00", "end_time": "17:00"}],
            "tuesday": [{"start_time": "09:00", "end_time": "17:00"}]
        })
    )
    db.add(owner_data)
    db.commit()
    db.refresh(owner_data)
    return owner_data

@pytest.fixture(scope="function")
def authenticated_client(client, test_owner):
    response = client.post(
        "/token",
        data={"username": test_owner.email, "password": "testpassword"},
    )
    assert response.status_code == 302
    access_token = response.cookies.get("access_token")
    assert access_token is not None
    
    client.headers["Authorization"] = f"Bearer {access_token}"
    yield client
    client.headers.pop("Authorization", None)
