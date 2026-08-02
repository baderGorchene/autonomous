import os
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from twilio.rest import Client
import logging
from src.config import settings
from src import schemas

logger = logging.getLogger(__name__)

def send_email(to_email: str, subject: str, html_content: str):
    if not settings.SENDGRID_API_KEY:
        logger.warning("SENDGRID_API_KEY not set. Email notification skipped.")
        return

    try:
        message = Mail(
            from_email='no-reply@bookslot.app',
            to_emails=to_email,
            subject=subject,
            html_content=html_content
        )
        sendgrid_client = SendGridAPIClient(settings.SENDGRID_API_KEY)
        response = sendgrid_client.send(message)
        logger.info(f"Email sent to {to_email}. Status Code: {response.status_code}")
    except Exception as e:
        logger.error(f"Error sending email to {to_email}: {e}")

def send_whatsapp_message(to_phone_number: str, message_body: str):
    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN or not settings.TWILIO_WHATSAPP_NUMBER:
        logger.warning("Twilio credentials not fully set. WhatsApp notification skipped.")
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

def send_booking_confirmation_email(owner_email: str, customer_email: str, booking_details: schemas.Booking, owner_name: str, business_name: str):
    subject_customer = f"Your booking with {business_name} is confirmed!"
    html_content_customer = f"""
    <html>
    <body>
        <p>Dear {booking_details.customer_name},</p>
        <p>Your booking for <b>{booking_details.service_name}</b> with {business_name} on <b>{booking_details.booking_date.isoformat()}</b> at <b>{booking_details.booking_time.isoformat()}</b> is confirmed!</p>
        <p>We look forward to seeing you.</p>
        <p>Best regards,</p>
        <p>{owner_name}</p>
    </body>
    </html>
    """
    send_email(customer_email, subject_customer, html_content_customer)

    subject_owner = f"New booking for {business_name} from {booking_details.customer_name}"
    html_content_owner = f"""
    <html>
    <body>
        <p>Dear {owner_name},</p>
        <p>You have a new booking:</p>
        <ul>
            <li>Customer: {booking_details.customer_name}</li>
            <li>Email: {booking_details.customer_email}</li>
            <li>Phone: {booking_details.customer_phone}</li>
            <li>Service: {booking_details.service_name}</li>
            <li>Date: {booking_details.booking_date.isoformat()}</li>
            <li>Time: {booking_details.booking_time.isoformat()}</li>
        </ul>
        <p>Please check your dashboard for more details.</p>
    </body>
    </html>
    """
    send_email(owner_email, subject_owner, html_content_owner)

def send_whatsapp_notification(owner_phone: str, customer_name: str, service_name: str, booking_date: str, booking_time: str):
    message_body = (
        f"New BookSlot booking!\n"
        f"Customer: {customer_name}\n"
        f"Service: {service_name}\n"
        f"Date: {booking_date}\n"
        f"Time: {booking_time}"
    )
    send_whatsapp_message(owner_phone, message_body)