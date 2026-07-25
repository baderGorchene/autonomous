from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from twilio.rest import Client
from .config import settings
import logging

logger = logging.getLogger(__name__)

def send_email_notification(to_email: str, subject: str, html_content: str):
    """Sends an email using SendGrid."""
    if not settings.SENDGRID_API_KEY or settings.SENDGRID_API_KEY == "dummy_sendgrid_key":
        logger.warning("SENDGRID_API_KEY is not set or is a dummy key. Skipping actual email notification.")
        print(f"DUMMY EMAIL (SendGrid): To: {to_email}, Subject: {subject}")
        return

    message = Mail(
        from_email='noreply@bookslot.app',
        to_emails=to_email,
        subject=subject,
        html_content=html_content
    )
    try:
        sendgrid_client = SendGridAPIClient(settings.SENDGRID_API_KEY)
        response = sendgrid_client.send(message)
        logger.info(f"Email sent to {to_email}. Status Code: {response.status_code}")
    except Exception as e:
        logger.error(f"Error sending email to {to_email}: {e}")
        print(f"DUMMY EMAIL (SendGrid) FAILED: To: {to_email}, Subject: {subject}, Error: {e}")


def send_whatsapp_notification(to_phone_number: str, message_body: str):
    """Sends a WhatsApp message using Twilio."""
    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN or not settings.TWILIO_WHATSAPP_NUMBER or settings.TWILIO_ACCOUNT_SID == "ACXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX":
        logger.warning("Twilio credentials not fully set or are dummy. Skipping actual WhatsApp notification.")
        print(f"DUMMY WHATSAPP (Twilio): To: {to_phone_number}, Message: {message_body}")
        return

    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        message = client.messages.create(
            from_=f'whatsapp:{settings.TWILIO_WHATSAPP_NUMBER}',
            body=message_body,
            to=f'whatsapp:{to_phone_number}'
        )
        logger.info(f"WhatsApp message sent to {to_phone_number}. SID: {message.sid}")
    except Exception as e:
        logger.error(f"Error sending WhatsApp message to {to_phone_number}: {e}")
        print(f"DUMMY WHATSAPP (Twilio) FAILED: To: {to_phone_number}, Message: {message_body}, Error: {e}")
