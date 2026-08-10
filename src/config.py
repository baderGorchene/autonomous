import os
from pydantic import BaseSettings

class Settings(BaseSettings):
    SECRET_KEY: str = "supersecretkey"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    STRIPE_API_KEY: str = "sk_test_..."
    STRIPE_WEBHOOK_SECRET: str = "whsec_..."
    STRIPE_PREMIUM_PRICE_ID: str = "price_123" # Example Price ID for premium plan

    SENDGRID_API_KEY: str = "SG...."
    TWILIO_ACCOUNT_SID: str = "AC...."
    TWILIO_AUTH_TOKEN: str = "your_auth_token"
    TWILIO_PHONE_NUMBER: str = "+1234567890"

    SQLALCHEMY_DATABASE_URL: str = "sqlite:///./sql_app.db"
    REDIS_URL: str = "redis://localhost:6379/0"

    class Config:
        env_file = ".env"
        env_file_encoding = 'utf-8'

settings = Settings()