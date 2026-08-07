from pydantic_settings import BaseSettings, SettingsConfigConfigDict
import os
from pydantic import Field

class Settings(BaseSettings):
    # SECRET_KEY should be a strong, randomly generated string in production
    # It is a critical security setting and must be explicitly set via an environment variable.
    SECRET_KEY: str = Field(..., min_length=32, description="Secret key for JWT. MUST be set via environment variable or .env file in production.")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # External service API keys. These are required for production and should be set via environment variables.
    SENDGRID_API_KEY: str = Field("", description="SendGrid API Key for email notifications. Required for production. Set via environment variable.")
    TWILIO_ACCOUNT_SID: str = Field("", description="Twilio Account SID for WhatsApp notifications. Required for production. Set via environment variable.")
    TWILIO_AUTH_TOKEN: str = Field("", description="Twilio Auth Token for WhatsApp notifications. Required for production. Set via environment variable.")
    TWILIO_WHATSAPP_NUMBER: str = Field("", description="Twilio WhatsApp Sender Number (e.g., 'whatsapp:+1234567890'). Required for production. Set via environment variable.")
    GEMINI_API_KEY: str = Field("", description="Gemini API Key (currently not used).")

    # Database configuration. SQLite is for development/MVP. PostgreSQL or similar is REQUIRED for production.
    DATABASE_URL: str = Field("sqlite:///./sql_app.db", description="Database URL. Use a production-grade DB like PostgreSQL in production. Set via environment variable.")
    TESTING: bool = False # Set to True for test environments, False for production.
    
    # Base URL for the application, used for generating links in emails/notifications.
    # IMPORTANT: Must be set to the public domain (e.g., "https://bookslot.app") in production.
    SERVER_NAME: str = Field("http://localhost:8000", description="Base URL of the application. Set to your public domain in production. Set via environment variable.")

    # Default locale for the application (e.g., 'en', 'ar', 'fr')
    DEFAULT_LOCALE: str = Field("en", description="Default language for the application. Can be set via environment variable.")

    _current_file_dir = os.path.dirname(os.path.abspath(__file__))
    PROJECT_ROOT = os.path.abspath(os.path.join(_current_file_dir, os.pardir))
    LOCALES_DIR: str = os.path.join(PROJECT_ROOT, 'locales')

    model_config = SettingsConfigConfigDict(env_file=".env", extra='ignore', env_file_encoding='utf-8')

settings = Settings()
