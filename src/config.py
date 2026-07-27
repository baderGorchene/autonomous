from pydantic_settings import BaseSettings, SettingsConfigDict
import os

class Settings(BaseSettings):
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    SENDGRID_API_KEY: str
    TWILIO_ACCOUNT_SID: str
    TWILIO_AUTH_TOKEN: str
    TWILIO_WHATSAPP_NUMBER: str
    GEMINI_API_KEY: str = ""
    DATABASE_URL: str

    # Determine the base directory of the project for locales
    # Assuming src/config.py is located at <project_root>/src/config.py
    _current_file_dir = os.path.dirname(os.path.abspath(__file__))
    PROJECT_ROOT = os.path.abspath(os.path.join(_current_file_dir, os.pardir))
    LOCALES_DIR: str = os.path.join(PROJECT_ROOT, 'locales')

    model_config = SettingsConfigDict(env_file=".env", extra='ignore')

settings = Settings()
