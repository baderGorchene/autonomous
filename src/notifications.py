import os
import logging
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from twilio.rest import Client
from .config import settings

logger = logging.getLogger(__name__)

def send_email(to_email: str, subject: str, html_content: str):
    if not settings.SENDGRID_API_KEY:
        logger.warning("SENDGRID_API_KEY is not set. Skipping email sending.")
        return False

    message = Mail(
        from_email='no-reply@bookslot.app', # Replace with your verified sender
        to_emails=to_email,
        subject=subject,
        html_content=html_content
    )
    try:
        sendgrid_client = SendGridAPIClient(settings.SENDGRID_API_KEY)
        response = sendgrid_client.send(message)
        logger.info(f"Email sent to {to_email}. Status Code: {response.status_code}")
        return True
    except Exception as e:
        logger.error(f"Error sending email to {to_email}: {e}")
        return False

def send_whatsapp_message(to_phone: str, body: str):
    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN or not settings.TWILIO_WHATSAPP_NUMBER:
        logger.warning("Twilio credentials or WhatsApp number not set. Skipping WhatsApp message.")
        return False

    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        message = client.messages.create(
            from_=f'whatsapp:{settings.TWILIO_WHATSAPP_NUMBER}',
            body=body,
            to=f'whatsapp:{to_phone}'
        )
        logger.info(f"WhatsApp message sent to {to_phone}. SID: {message.sid}")
        return True
    except Exception as e:
        logger.error(f"Error sending WhatsApp message to {to_phone}: {e}")
        return False

# Placeholder for email templates
def get_booking_confirmation_email_content(owner_name: str, customer_name: str, service_name: str, booking_date: str, booking_time: str, owner_phone: str, customer_phone: str, owner_email: str) -> str:
    return f"""
    <html>
    <body>
        <p>Dear {customer_name},</p>
        <p>Your booking with {owner_name} for {service_name} on {booking_date} at {booking_time} has been confirmed!</p>
        <p>Owner contact: {owner_phone} / {owner_email}</p>
        <p>Customer contact: {customer_phone}</p>
        <p>Thank you!</p>
    </body>
    </html>
    """

def get_owner_new_booking_email_content(owner_name: str, customer_name: str, customer_email: str, customer_phone: str, service_name: str, booking_date: str, booking_time: str) -> str:
    return f"""
    <html>
    <body>
        <p>Dear {owner_name},</p>
        <p>You have a new booking!</p>
        <p>Customer: {customer_name} ({customer_email}, {customer_phone})</p>
        <p>Service: {service_name}</p>
        <p>Date: {booking_date}</p>
        <p>Time: {booking_time}</p>
        <p>Please prepare for your appointment.</p>
    </body>
    </html>
    """

def get_owner_new_booking_whatsapp_content(owner_name: str, customer_name: str, customer_email: str, customer_phone: str, service_name: str, booking_date: str, booking_time: str) -> str:
    return f"""
    Hello {owner_name}, you have a new booking!
    Customer: {customer_name} ({customer_email}, {customer_phone})
    Service: {service_name}
    Date: {booking_date}
    Time: {booking_time}
    """
