# src/notifications.py
from src.config import settings
import logging

logger = logging.getLogger(__name__)

def send_email_notification(to_email: str, subject: str, body: str):
    logger.info(f"Sending email to {to_email} with subject '{subject}':\n{body}")

def send_whatsapp_notification(to_phone: str, message: str):
    logger.info(f"Sending WhatsApp to {to_phone}: {message}")
