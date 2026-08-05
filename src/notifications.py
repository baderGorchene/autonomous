import os
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from twilio.rest import Client
from src.config import settings
import logging

logger = logging.getLogger(__name__)

def send_email_notification(to_email: str, subject: str, html_content: str):
    if not settings.SENDGRID_API_KEY:
        logger.warning("SendGrid API key not configured. Email notification skipped.")
        return False
    
    message = Mail(
        from_email='no-reply@bookslot.app', # Replace with your verified sender email
        to_emails=to_email,
        subject=subject,
        html_content=html_content)
    try:
        sendgrid_client = SendGridAPIClient(settings.SENDGRID_API_KEY)
        response = sendgrid_client.send(message)
        logger.info(f"Email sent to {to_email} with status code: {response.status_code}")
        return True
    except Exception as e:
        logger.error(f"Error sending email to {to_email}: {e}")
        return False

def send_whatsapp_notification(to_phone: str, message_body: str):
    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN or not settings.TWILIO_WHATSAPP_NUMBER:
        logger.warning("Twilio credentials not fully configured. WhatsApp notification skipped.")
        return False

    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        message = client.messages.create(
            from_=settings.TWILIO_WHATSAPP_NUMBER,
            body=message_body,
            to=f"whatsapp:{to_phone}"
        )
        logger.info(f"WhatsApp message sent to {to_phone} with SID: {message.sid}")
        return True
    except Exception as e:
        logger.error(f"Error sending WhatsApp message to {to_phone}: {e}")
        return False
