import os
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from twilio.rest import Client
import logging
from fastapi.templating import Jinja2Templates
from src.config import settings
from src.i18n_config import get_jinja_env # Import to get locale-specific env for email templates

logger = logging.getLogger(__name__)

# Re-initialize templates here for email rendering, distinct from main.py's app templates
# This ensures that email templates can be rendered independently, potentially with different locales.
EMAIL_TEMPLATES_DIR = os.path.join(settings.PROJECT_ROOT, 'templates')

def render_email_template(template_name: str, template_data: dict, lang: str = 'en') -> str:
    env = get_jinja_env(locale=lang)
    template = env.get_template(template_name)
    return template.render(template_data)

def send_email(to_email: str, subject: str, template_name: str, template_data: dict):
    if not settings.SENDGRID_API_KEY:
        logger.warning("SENDGRID_API_KEY is not set. Skipping email sending.")
        return

    try:
        html_content = render_email_template(template_name, template_data, lang=template_data.get('lang', 'en'))
        message = Mail(
            from_email='no-reply@bookslot.app', # Replace with your verified sender
            to_emails=to_email,
            subject=subject,
            html_content=html_content
        )
        sg = SendGridAPIClient(settings.SENDGRID_API_KEY)
        response = sg.send(message)
        logger.info(f"Email sent to {to_email} with status code: {response.status_code}")
    except Exception as e:
        logger.error(f"Error sending email to {to_email}: {e}")

def send_whatsapp_message(to_phone_number: str, message: str, lang: str = 'en'):
    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN or not settings.TWILIO_WHATSAPP_NUMBER:
        logger.warning("Twilio credentials or WhatsApp number not set. Skipping WhatsApp message.")
        return

    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        # Twilio WhatsApp numbers usually start with "whatsapp:+"
        from_whatsapp_number = f"whatsapp:{settings.TWILIO_WHATSAPP_NUMBER}"
        to_whatsapp_number = f"whatsapp:{to_phone_number}"

        message = client.messages.create(
            from_=from_whatsapp_number,
            body=message,
            to=to_whatsapp_number
        )
        logger.info(f"WhatsApp message sent to {to_phone_number}, SID: {message.sid}")
    except Exception as e:
        logger.error(f"Error sending WhatsApp message to {to_phone_number}: {e}")