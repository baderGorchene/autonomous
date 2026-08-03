from pydantic_settings import BaseSettings, SettingsConfigDict
import os

class Settings(BaseSettings):
    # !!! IMPORTANT: Change this in production and keep it secret !!!
    SECRET_KEY: str = "super-secret-key"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    SENDGRID_API_KEY: str = ""
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_WHATSAPP_NUMBER: str = ""
    GEMINI_API_KEY: str = "" # Currently not used in the application

    DATABASE_URL: str = "sqlite:///./sql_app.db" # Use PostgreSQL in production
    TESTING: bool = False

    _current_file_dir = os.path.dirname(os.path.abspath(__file__))
    PROJECT_ROOT = os.path.abspath(os.path.join(_current_file_dir, os.pardir))
    LOCALES_DIR: str = os.path.join(PROJECT_ROOT, 'locales')

    model_config = SettingsConfigDict(env_file=".env", extra='ignore', env_file_encoding='utf-8')

settings = Settings()
