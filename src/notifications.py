from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from twilio.rest import Client
from .config import settings
import logging

logger = logging.getLogger(__name__)

def send_email_notification(to_email: str, subject: str, html_content: str):
    if not settings.SENDGRID_API_KEY:
        logger.warning("SendGrid API key not set. Email notification skipped for %s", to_email)
        return False

    message = Mail(
        from_email='no-reply@bookslot.app', # Replace with your verified sender email
        to_emails=to_email,
        subject=subject,
        html_content=html_content
    )
    try:
        sendgrid_client = SendGridAPIClient(settings.SENDGRID_API_KEY)
        response = sendgrid_client.send(message)
        logger.info("Email sent to %s, Status Code: %s", to_email, response.status_code)
        return True
    except Exception as e:
        logger.error("Error sending email to %s: %s", to_email, e)
        return False

def send_whatsapp_notification(to_phone: str, message_body: str):
    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN or not settings.TWILIO_WHATSAPP_NUMBER:
        logger.warning("Twilio credentials not fully set. WhatsApp notification skipped for %s", to_phone)
        return False

    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        message = client.messages.create(
            from_=f'whatsapp:{settings.TWILIO_WHATSAPP_NUMBER}',
            body=message_body,
            to=f'whatsapp:{to_phone}'
        )
        logger.info("WhatsApp message sent to %s, SID: %s", to_phone, message.sid)
        return True
    except Exception as e:
        logger.error("Error sending WhatsApp message to %s: %s", to_phone, e)
        return False

def send_booking_confirmation_to_customer(booking_details: dict, owner_details: dict, locale: str = 'en'):
    # This will be handled by the main.py using gettext
    pass

def send_booking_notification_to_owner(booking_details: dict, owner_details: dict, locale: str = 'en'):
    # This will be handled by the main.py using gettext
    pass
