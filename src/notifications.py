from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from twilio.rest import Client
from .config import settings
import logging

logger = logging.getLogger(__name__)

def send_email_notification(to_email: str, subject: str, html_content: str):
    """Sends an email using SendGrid."""
    if not settings.SENDGRID_API_KEY or settings.SENDGRID_API_KEY == "SG....":
        logger.warning(f"SendGrid API key not configured. Skipping email to {to_email}.")
        return

    message = Mail(
        from_email='noreply@bookslot.app',
        to_emails=to_email,
        subject=subject,
        html_content=html_content)
    try:
        sendgrid_client = SendGridAPIClient(settings.SENDGRID_API_KEY)
        response = sendgrid_client.send(message)
        logger.info(f"Email sent to {to_email}. Status Code: {response.status_code}")
    except Exception as e:
        logger.error(f"Error sending email to {to_email}: {e}")

def send_sms_notification(to_phone_number: str, message_body: str):
    """Sends an SMS using Twilio."""
    if not settings.TWILIO_ACCOUNT_SID or settings.TWILIO_ACCOUNT_SID == "AC....":
        logger.warning(f"Twilio credentials not configured. Skipping SMS to {to_phone_number}.")
        return

    if not to_phone_number.startswith('+'):
        logger.warning(f"Phone number {to_phone_number} does not include country code. Skipping SMS.")
        return

    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        message = client.messages.create(
            to=to_phone_number,
            from_=settings.TWILIO_PHONE_NUMBER,
            body=message_body
        )
        logger.info(f"SMS sent to {to_phone_number}. SID: {message.sid}")
    except Exception as e:
        logger.error(f"Error sending SMS to {to_phone_number}: {e}")

def send_booking_confirmation(booking: 'models.Booking', service: 'models.Service', owner: 'models.Owner'):
    owner_subject = f"New Booking for {service.name} from {booking.customer_name}"
    owner_html = f"""
        <h1>New Booking!</h1>
        <p>A new booking has been made:</p>
        <ul>
            <li>Service: {service.name}</li>
            <li>Date: {booking.date}</li>
            <li>Time: {booking.time}</li>
            <li>Customer Name: {booking.customer_name}</li>
            <li>Customer Email: {booking.customer_email}</li>
            <li>Customer Phone: {booking.customer_phone or 'N/A'}</li>
        </ul>
        <p>Login to your dashboard to view: bookslot.app/dashboard</p>
    """
    send_email_notification(owner.email, owner_subject, owner_html)
    if owner.phone:
        owner_sms = f"New booking for {service.name} on {booking.date} at {booking.time} by {booking.customer_name}. Check dashboard."
        send_sms_notification(owner.phone, owner_sms)

    customer_subject = f"Your Booking Confirmation for {service.name}"
    customer_html = f"""
        <h1>Booking Confirmed!</h1>
        <p>Dear {booking.customer_name},</p>
        <p>Your booking for {service.name} on {booking.date} at {booking.time} has been confirmed.</p>
        <p>We look forward to seeing you!</p>
    """
    send_email_notification(booking.customer_email, customer_subject, customer_html)
    if booking.customer_phone:
        customer_sms = f"Your booking for {service.name} on {booking.date} at {booking.time} is confirmed. See you then!"
        send_sms_notification(booking.customer_phone, customer_sms)