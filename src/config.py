from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    SECRET_KEY: str = "your-super-secret-key"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # Environment variables for external services
    SENDGRID_API_KEY: str
    TWILIO_ACCOUNT_SID: str
    TWILIO_AUTH_TOKEN: str
    TWILIO_WHATSAPP_NUMBER: str
    GEMINI_API_KEY: str = "" # Made optional
    DATABASE_URL: str = "sqlite:///./bookslot.db" # Added DATABASE_URL

    model_config = SettingsConfigDict(env_file=".env", extra='ignore')

settings = Settings()
