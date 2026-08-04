from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from twilio.rest import Client
from src.config import settings
from . import models
import logging

logger = logging.getLogger(__name__)

def send_email(to_email: str, subject: str, html_content: str):
    if not settings.SENDGRID_API_KEY:
        logger.warning("SendGrid API key not configured. Email will not be sent.")
        return

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
    except Exception as e:
        logger.error(f"Error sending email to {to_email}: {e}")

def send_whatsapp_message(to_phone: str, message_body: str):
    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN or not settings.TWILIO_WHATSAPP_NUMBER:
        logger.warning("Twilio credentials or WhatsApp number not configured. WhatsApp message will not be sent.")
        return

    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        # Twilio requires phone numbers in E.164 format for WhatsApp, e.g., whatsapp:+1234567890
        # The `to_phone` argument should already be in E.164 format (e.g., +1234567890)
        # Twilio WhatsApp numbers typically start with 'whatsapp:'
        from_whatsapp_number = f"whatsapp:{settings.TWILIO_WHATSAPP_NUMBER}"
        to_whatsapp_number = f"whatsapp:{to_phone}"

        message = client.messages.create(
            from_=from_whatsapp_number,
            body=message_body,
            to=to_whatsapp_number
        )
        logger.info(f"WhatsApp message sent to {to_phone}. SID: {message.sid}")
    except Exception as e:
        logger.error(f"Error sending WhatsApp message to {to_phone}: {e}")

def send_owner_notification(owner: models.Owner, booking: models.Booking):
    subject = f"New Booking for {owner.business_name}"
    html_content = f"""
    <html>
    <body>
        <p>Hello {owner.name},</p>
        <p>You have a new booking!</p>
        <p><strong>Customer:</strong> {booking.customer_name}</p>
        <p><strong>Service:</strong> {booking.service_name}</p>
        <p><strong>Date:</strong> {booking.booking_date.strftime('%Y-%m-%d')}</p>
        <p><strong>Time:</strong> {booking.booking_time.strftime('%H:%M')}</p>
        <p><strong>Customer Email:</strong> {booking.customer_email}</p>
        <p><strong>Customer Phone:</strong> {booking.customer_phone or 'N/A'}</p>
        <p>Manage your bookings: <a href="https://bookslot.app/dashboard">BookSlot Dashboard</a></p>
    </body>
    </html>
    """
    send_email(owner.email, subject, html_content)

    if owner.phone:
        whatsapp_message = (
            f"New Booking for {owner.business_name}:\n"
            f"Customer: {booking.customer_name}\n"
            f"Service: {booking.service_name}\n"
            f"Date: {booking.booking_date.strftime('%Y-%m-%d')}\n"
            f"Time: {booking.booking_time.strftime('%H:%M')}\n"
            f"Customer Phone: {booking.customer_phone or 'N/A'}"
        )
        send_whatsapp_message(owner.phone, whatsapp_message)


def send_customer_confirmation(owner: models.Owner, booking: models.Booking):
    subject = f"Your Booking Confirmation with {owner.business_name}"
    html_content = f"""
    <html>
    <body>
        <p>Hello {booking.customer_name},</p>
        <p>Your booking with {owner.business_name} has been confirmed!</p>
        <p><strong>Service:</strong> {booking.service_name}</p>
        <p><strong>Date:</strong> {booking.booking_date.strftime('%Y-%m-%d')}</p>
        <p><strong>Time:</strong> {booking.booking_time.strftime('%H:%M')}</p>
        <p>We look forward to seeing you!</p>
        <p>Best regards,<br>{owner.business_name}</p>
    </body>
    </html>
    """
    send_email(booking.customer_email, subject, html_content)

    if booking.customer_phone:
        whatsapp_message = (
            f"Hi {booking.customer_name},\n"
            f"Your booking with {owner.business_name} is confirmed!\n"
            f"Service: {booking.service_name}\n"
            f"Date: {booking.booking_date.strftime('%Y-%m-%d')}\n"
            f"Time: {booking.booking_time.strftime('%H:%M')}\n"
            f"See you soon!"
        )
        send_whatsapp_message(booking.customer_phone, whatsapp_message)
