import os
from pydantic import BaseSettings

class Settings(BaseSettings):
    SECRET_KEY: str = "supersecretkey" # WARNING: Change this in production! Use a strong, random string.
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    STRIPE_API_KEY: str = "sk_test_..." # WARNING: Set in .env for production!
    STRIPE_WEBHOOK_SECRET: str = "whsec_..." # WARNING: Set in .env for production!
    STRIPE_PREMIUM_PRICE_ID: str = "price_123" # Example Price ID for premium plan, set in .env for production

    SENDGRID_API_KEY: str = "SG...." # WARNING: Set in .env for production!
    TWILIO_ACCOUNT_SID: str = "AC...." # WARNING: Set in .env for production!
    TWILIO_AUTH_TOKEN: str = "your_auth_token" # WARNING: Set in .env for production!
    TWILIO_PHONE_NUMBER: str = "+1234567890" # WARNING: Set in .env for production!

    SQLALCHEMY_DATABASE_URL: str = "sqlite:///./sql_app.db" # WARNING: Use PostgreSQL or similar in production!
    REDIS_URL: str = "redis://localhost:6379/0" # WARNING: Configure for production environment!

    class Config:
        env_file = ".env"
        env_file_encoding = 'utf-8'

settings = Settings()