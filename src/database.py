from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from .config import settings

# This DATABASE_URL will be used by default, but can be overridden for tests
DATABASE_URL = settings.DATABASE_URL

# The `connect_args={"check_same_thread": False}` is important for SQLite
# if multiple threads access the database, which can happen in FastAPI.
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Dependency to get a database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# This function can be called to create tables, e.g., at app startup or in tests
def create_tables():
    Base.metadata.create_all(bind=engine)
