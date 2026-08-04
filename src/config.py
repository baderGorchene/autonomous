from pydantic_settings import BaseSettings, SettingsConfigDict
import os
from pydantic import Field

class Settings(BaseSettings):
    # SECRET_KEY should be a strong, randomly generated string in production
    SECRET_KEY: str = Field(..., min_length=32, description="Secret key for JWT. Must be set via environment variable or .env file.")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    SENDGRID_API_KEY: str = Field("", description="SendGrid API Key for email notifications.")
    TWILIO_ACCOUNT_SID: str = Field("", description="Twilio Account SID for WhatsApp notifications.")
    TWILIO_AUTH_TOKEN: str = Field("", description="Twilio Auth Token for WhatsApp notifications.")
    TWILIO_WHATSAPP_NUMBER: str = Field("", description="Twilio WhatsApp Sender Number (e.g., 'whatsapp:+1234567890').")
    GEMINI_API_KEY: str = Field("", description="Gemini API Key (currently not used).")

    DATABASE_URL: str = "sqlite:///./sql_app.db"
    TESTING: bool = False
    
    # Base URL for the application, used for generating links in emails/notifications
    # e.g., "https://bookslot.app" or "http://localhost:8000"
    SERVER_NAME: str = Field("http://localhost:8000", description="Base URL of the application.")

    _current_file_dir = os.path.dirname(os.path.abspath(__file__))
    PROJECT_ROOT = os.path.abspath(os.path.join(_current_file_dir, os.pardir))
    LOCALES_DIR: str = os.path.join(PROJECT_ROOT, 'locales')

    model_config = SettingsConfigDict(env_file=".env", extra='ignore', env_file_encoding='utf-8')

settings = Settings()
