from pydantic_settings import BaseSettings, SettingsConfigDict
import os

class Settings(BaseSettings):
    # !!! IMPORTANT: Change this to a strong, randomly generated key for production.
    # Use `openssl rand -hex 32` or similar to generate a secure key.
    SECRET_KEY: str = "super-secret-key"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    SENDGRID_API_KEY: str = "" # Made optional for dev/test without actual keys
    TWILIO_ACCOUNT_SID: str = "" # Made optional for dev/test without actual keys
    TWILIO_AUTH_TOKEN: str = "" # Made optional for dev/test without actual keys
    TWILIO_WHATSAPP_NUMBER: str = "" # Made optional for dev/test without actual keys
    GEMINI_API_KEY: str = ""

    DATABASE_URL: str = "sqlite:///./sql_app.db" # Default for non-testing, overridden for tests
    TESTING: bool = False # New flag to indicate testing environment

    _current_file_dir = os.path.dirname(os.path.abspath(__file__))
    PROJECT_ROOT = os.path.abspath(os.path.join(_current_file_dir, os.pardir))
    LOCALES_DIR: str = os.path.join(PROJECT_ROOT, 'locales')

    model_config = SettingsConfigDict(env_file=".env", extra='ignore')

settings = Settings()
