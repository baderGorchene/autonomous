import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from src.main import app
from src.database import Base, get_db
from src.config import settings
from src import models

# Override database settings for testing
settings.DATABASE_URL = "sqlite:///./test_sql_app.db"
settings.TESTING = True

# Setup test database
connect_args = {"check_same_thread": False}
engine = create_engine(settings.DATABASE_URL, **connect_args)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(name="db_session")
def db_session_fixture():
    Base.metadata.create_all(bind=engine)  # Create tables
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)  # Drop tables after tests

@pytest.fixture(name="client")
def client_fixture(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            db_session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()

def test_health_check(client, db_session):
    # Ensure the database is accessible for the health check
    db_session.execute(text("SELECT 1"))
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_health_check_db_failure(client, mocker):
    # Mock the database session to raise an exception
    mocker.patch("src.database.get_db", side_effect=Exception("DB error"))
    response = client.get("/health")
    assert response.status_code == 500
    assert response.json() == {"detail": "Database connection failed"}

# More tests will be added here for owner signup, login, dashboard, booking, i18n, etc.
