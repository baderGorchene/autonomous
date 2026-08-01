import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.main import app, get_db, get_current_active_owner_optional, get_current_active_owner
from src.database import Base
from src.config import settings
from src.models import Owner
from src import security

# Override settings for testing
settings.TESTING = True

# Setup a new engine and session for testing using in-memory SQLite
TEST_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(name="db_session")
def db_session_fixture():
    Base.metadata.create_all(bind=engine)  # Create tables
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine) # Drop tables after test

@pytest.fixture(name="client")
def client_fixture(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    # Mock authentication for public pages by default
    app.dependency_overrides[get_current_active_owner_optional] = lambda: None 
    app.dependency_overrides[get_current_active_owner] = lambda: None 

    with TestClient(app) as test_client:
        yield test_client

# Basic test for health endpoint
def test_read_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

# Test owner signup
def test_create_owner_signup(client, db_session):
    owner_data = {
        "name": "Test Owner",
        "email": "test@example.com",
        "password": "testpassword",
        "business_name": "Test Business",
        "slug": "test-business",
        "phone": "+1234567890"
    }
    response = client.post("/signup", data=owner_data)
    assert response.status_code == 200
    assert "Owner registered successfully" in response.text

    # Verify owner in DB
    owner_in_db = db_session.query(Owner).filter(Owner.email == owner_data["email"]).first()
    assert owner_in_db is not None
    assert owner_in_db.name == owner_data["name"]

# Test owner login
def test_owner_login_success(client, db_session):
    # First, create an owner
    owner_data = {
        "name": "Login Owner",
        "email": "login@example.com",
        "password": "loginpassword",
        "business_name": "Login Business",
        "slug": "login-business",
        "phone": "+1987654321"
    }
    hashed_password = security.get_password_hash(owner_data["password"])
    db_owner = Owner(
        name=owner_data["name"],
        email=owner_data["email"],
        hashed_password=hashed_password,
        business_name=owner_data["business_name"],
        slug=owner_data["slug"],
        services_json="[]",
        availability_json="{}",
        phone=owner_data["phone"]
    )
    db_session.add(db_owner)
    db_session.commit()
    db_session.refresh(db_owner)

    # Now, try to log in
    login_data = {
        "username": owner_data["email"], # FastAPI uses 'username' for OAuth2PasswordRequestForm
        "password": owner_data["password"]
    }
    response = client.post("/token", data=login_data)
    assert response.status_code == 200
    assert "access_token" in response.json()
    assert response.json()["token_type"] == "bearer"

def test_owner_login_fail_bad_password(client, db_session):
    # First, create an owner
    owner_data = {
        "name": "Login Owner Fail",
        "email": "login_fail@example.com",
        "password": "loginpassword_fail",
        "business_name": "Login Business Fail",
        "slug": "login-business-fail",
        "phone": "+1122334455"
    }
    hashed_password = security.get_password_hash(owner_data["password"])
    db_owner = Owner(
        name=owner_data["name"],
        email=owner_data["email"],
        hashed_password=hashed_password,
        business_name=owner_data["business_name"],
        slug=owner_data["slug"],
        services_json="[]",
        availability_json="{}",
        phone=owner_data["phone"]
    )
    db_session.add(db_owner)
    db_session.commit()
    db_session.refresh(db_owner)

    # Now, try to log in with bad password
    login_data = {
        "username": owner_data["email"],
        "password": "wrongpassword"
    }
    response = client.post("/token", data=login_data)
    assert response.status_code == 400
    assert response.json() == {"detail": "Incorrect username or password"}
