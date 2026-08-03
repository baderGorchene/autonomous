from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from twilio.rest import Client
import logging
from src.config import settings
import gettext
import os

logger = logging.getLogger(__name__)

# Setup gettext for notifications
_current_file_dir = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(_current_file_dir, os.pardir))
LOCALES_DIR = os.path.join(PROJECT_ROOT, 'locales')

def get_notification_translator(language: str):
    try:
        return gettext.translation('messages', LOCALES_DIR, languages=[language], fallback=True)
    except Exception as e:
        logger.warning(f"Could not load translations for notification locale '{language}': {e}")
        return gettext.NullTranslations()

def send_email(to_email: str, subject: str, html_content: str):
    if not settings.SENDGRID_API_KEY:
        logger.warning("SENDGRID_API_KEY is not set. Email will not be sent.")
        return

    message = Mail(
        from_email='no-reply@bookslot.app', # Replace with your verified sender email
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

def send_whatsapp_message(to_phone_number: str, message_body: str):
    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN or not settings.TWILIO_WHATSAPP_NUMBER:
        logger.warning("Twilio credentials or WhatsApp number not set. WhatsApp message will not be sent.")
        return

    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        # Twilio requires phone numbers in E.164 format for WhatsApp, e.g., '+12345678900'
        # And the 'from_' number must be a Twilio WhatsApp enabled number, e.g., 'whatsapp:+14155238886'
        message = client.messages.create(
            from_=f"whatsapp:{settings.TWILIO_WHATSAPP_NUMBER}",
            body=message_body,
            to=f"whatsapp:{to_phone_number}"
        )
        logger.info(f"WhatsApp message sent to {to_phone_number}. SID: {message.sid}")
    except Exception as e:
        logger.error(f"Error sending WhatsApp message to {to_phone_number}: {e}")

def send_owner_notification(owner_email: str, owner_phone: str, customer_name: str, service_name: str, booking_date: str, booking_time: str, language: str = "en"):
    translator = get_notification_translator(language)
    _ = translator.gettext

    subject = _("New Booking Received for {service_name}").format(service_name=service_name)
    email_content = _("""
        <p>Dear {owner_name},</p>
        <p>You have received a new booking!</p>
        <ul>
            <li><strong>Customer:</strong> {customer_name}</li>
            <li><strong>Service:</strong> {service_name}</li>
            <li><strong>Date:</strong> {booking_date}</li>
            <li><strong>Time:</strong> {booking_time}</li>
        </ul>
        <p>Please check your dashboard for more details.</p>
        <p>Thank you,<br>BookSlot Team</p>
    """).format(
        owner_name="Owner", # Placeholder, owner's name might not be passed here
        customer_name=customer_name,
        service_name=service_name,
        booking_date=booking_date,
        booking_time=booking_time
    )
    send_email(owner_email, subject, email_content)

    whatsapp_content = _("New booking: {customer_name} for {service_name} on {booking_date} at {booking_time}.").format(
        customer_name=customer_name,
        service_name=service_name,
        booking_date=booking_date,
        booking_time=booking_time
    )
    if owner_phone:
        send_whatsapp_message(owner_phone, whatsapp_content)

def send_customer_confirmation(customer_email: str, customer_phone: str, owner_name: str, business_name: str, service_name: str, booking_date: str, booking_time: str, language: str = "en"):
    translator = get_notification_translator(language)
    _ = translator.gettext

    subject = _("Your Booking Confirmation with {business_name}").format(business_name=business_name)
    email_content = _("""
        <p>Dear {customer_name},</p>
        <p>Your booking with {business_name} has been confirmed!</p>
        <ul>
            <li><strong>Service:</strong> {service_name}</li>
            <li><strong>Date:</strong> {booking_date}</li>
            <li><strong>Time:</strong> {booking_time}</li>
            <li><strong>Business:</strong> {business_name} ({owner_name})</li>
        </ul>
        <p>We look forward to seeing you!</p>
        <p>Thank you,<br>{business_name}</p>
    """).format(
        customer_name="Customer", # Placeholder, customer's name might not be passed here
        business_name=business_name,
        owner_name=owner_name,
        service_name=service_name,
        booking_date=booking_date,
        booking_time=booking_time
    )
    send_email(customer_email, subject, email_content)

    whatsapp_content = _("Your booking with {business_name} for {service_name} on {booking_date} at {booking_time} is confirmed!").format(
        business_name=business_name,
        service_name=service_name,
        booking_date=booking_date,
        booking_time=booking_time
    )
    if customer_phone:
        send_whatsapp_message(customer_phone, whatsapp_content)
