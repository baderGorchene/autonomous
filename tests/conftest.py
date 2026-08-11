import pytest
from httpx import Client
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.database import Base, get_db
from src.main import app
from src.config import settings
from datetime import date, timedelta

# Use a separate test database
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_bookslot.db"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

@pytest.fixture(scope="function")
def db_session():
    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)
    yield session
    session.close()
    transaction.rollback()
    connection.close()

@pytest.fixture(scope="function")
def client(db_session):
    def override_get_db():
        yield db_session
    app.dependency_overrides[get_db] = override_get_db
    with Client(app=app, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()

# Helper for owner login
def owner_login(client: Client, email: str, password: str):
    response = client.post("/owner/token", data={"username": email, "password": password})
    response.raise_for_status()
    return response.json()["access_token"]

# Helper for future dates to avoid issues with current date bookings
@pytest.helpers.register
def future_date(days: int = 1):
    return date.today() + timedelta(days=days)
