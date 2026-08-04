from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from twilio.rest import Client
from src.config import settings
import logging

logger = logging.getLogger(__name__)

def send_email_notification(to_email: str, subject: str, html_content: str):
    """Sends an email using SendGrid."""
    if not settings.SENDGRID_API_KEY:
        logger.warning("SendGrid API key not configured. Email notification skipped for: %s", to_email)
        return False

    message = Mail(
        from_email='no-reply@bookslot.app', # Replace with your verified sender email
        to_emails=to_email,
        subject=subject,
        html_content=html_content
    )
    try:
        sg = SendGridAPIClient(settings.SENDGRID_API_KEY)
        response = sg.send(message)
        logger.info(f"Email sent to {to_email}. Status Code: {response.status_code}")
        return True
    except Exception as e:
        logger.error(f"Error sending email to {to_email}: {e}")
        return False

def send_whatsapp_notification(to_phone: str, message_body: str):
    """Sends a WhatsApp message using Twilio."""
    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN or not settings.TWILIO_WHATSAPP_NUMBER:
        logger.warning("Twilio credentials not fully configured. WhatsApp notification skipped for: %s", to_phone)
        return False

    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        message = client.messages.create(
            from_=f'whatsapp:{settings.TWILIO_WHATSAPP_NUMBER}',
            body=message_body,
            to=f'whatsapp:{to_phone}'
        )
        logger.info(f"WhatsApp message sent to {to_phone}. SID: {message.sid}")
        return True
    except Exception as e:
        logger.error(f"Error sending WhatsApp message to {to_phone}: {e}")
        return False

def format_booking_details(booking_data: dict, owner_name: str, business_name: str, language: str = "en") -> dict:
    # This function would be more complex with i18n, but for now, simple English.
    # The language parameter is kept for future expansion.
    subject_owner = f"New Booking for {business_name}!"
    subject_customer = f"Your Booking with {business_name} is Confirmed!"

    owner_email_html = f"""
    <html>
        <body>
            <p>Hello {owner_name},</p>
            <p>You have a new booking!</p>
            <p><strong>Customer Name:</strong> {booking_data['customer_name']}</p>
            <p><strong>Customer Email:</strong> {booking_data['customer_email']}</p>
            <p><strong>Customer Phone:</strong> {booking_data['customer_phone'] or 'N/A'}</p>
            <p><strong>Service:</strong> {booking_data['service_name']}</p>
            <p><strong>Date:</strong> {booking_data['booking_date']}</p>
            <p><strong>Time:</strong> {booking_data['booking_time']}</p>
            <p>Thank you!</p>
        </body>
    </html>
    """

    customer_email_html = f"""
    <html>
        <body>
            <p>Hello {booking_data['customer_name']},</p>
            <p>Your booking with {business_name} is confirmed!</p>
            <p><strong>Service:</strong> {booking_data['service_name']}</p>
            <p><strong>Date:</strong> {booking_data['booking_date']}</p>
            <p><strong>Time:</strong> {booking_data['booking_time']}</p>
            <p>We look forward to seeing you!</p>
            <p>Best regards,<br>{business_name}</p>
        </body>
    </html>
    """

    owner_whatsapp_msg = (
        f"New Booking for {business_name}!\n"
        f"Customer: {booking_data['customer_name']}\n"
        f"Email: {booking_data['customer_email']}\n"
        f"Phone: {booking_data['customer_phone'] or 'N/A'}\n"
        f"Service: {booking_data['service_name']}\n"
        f"Date: {booking_data['booking_date']}\n"
        f"Time: {booking_data['booking_time']}"
    )

    return {
        "owner_email_subject": subject_owner,
        "owner_email_html": owner_email_html,
        "customer_email_subject": subject_customer,
        "customer_email_html": customer_email_html,
        "owner_whatsapp_msg": owner_whatsapp_msg,
    }
