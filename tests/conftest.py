import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.database import Base, get_db as db_get_db
from src.main import app, get_db as main_get_db


SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
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
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    app.dependency_overrides[db_get_db] = override_get_db
    app.dependency_overrides[main_get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def db(db_session):
    return db_session

@pytest.fixture
def test_owner(db_session):
    from src import models, security
    hashed_pwd = security.get_password_hash("testpassword")
    owner = models.Owner(
        email="testowner@example.com",
        hashed_password=hashed_pwd,
        name="Test Owner",
        business_name="Test Business",
        slug="test-business-slug",
        phone="+1234567890",
        is_active=True
    )
    db_session.add(owner)
    db_session.commit()
    db_session.refresh(owner)
    return owner

@pytest.fixture
def test_service(db_session, test_owner):
    from src import models
    service = models.Service(
        name="Standard Haircut",
        description="Standard haircut service",
        duration_minutes=30,
        price=30,
        owner_id=test_owner.id
    )
    db_session.add(service)
    db_session.commit()
    db_session.refresh(service)
    return service

@pytest.fixture
def authenticated_client(client, test_owner):
    from src import security
    token = security.create_access_token(data={"sub": str(test_owner.id)})
    client.cookies.set("access_token", token)
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client

