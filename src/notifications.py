import os
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from twilio.rest import Client
from src.config import settings
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Initialize SendGrid client
sendgrid_client = SendGridAPIClient(settings.SENDGRID_API_KEY) if settings.SENDGRID_API_KEY else None

# Initialize Twilio client
twilio_client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN) if settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN else None


def send_email(to_email: str, subject: str, html_content: str):
    if not sendgrid_client:
        logger.warning("SendGrid API key not configured. Email not sent.")
        return False

    message = Mail(
        from_email='no-reply@bookslot.app', # Replace with your verified sender email
        to_emails=to_email,
        subject=subject,
        html_content=html_content
    )
    try:
        response = sendgrid_client.send(message)
        logger.info(f"Email sent to {to_email}. Status Code: {response.status_code}")
        return response.status_code < 400
    except Exception as e:
        logger.error(f"Error sending email to {to_email}: {e}")
        return False

def send_whatsapp_message(to_phone_number: str, message_body: str):
    if not twilio_client or not settings.TWILIO_WHATSAPP_NUMBER:
        logger.warning("Twilio or Twilio WhatsApp number not configured. WhatsApp message not sent.")
        return False

    try:
        message = twilio_client.messages.create(
            from_=f'whatsapp:{settings.TWILIO_WHATSAPP_NUMBER}',
            to=f'whatsapp:{to_phone_number}',
            body=message_body
        )
        logger.info(f"WhatsApp message sent to {to_phone_number}. SID: {message.sid}")
        return True
    except Exception as e:
        logger.error(f"Error sending WhatsApp message to {to_phone_number}: {e}")
        return False

def send_booking_confirmation_notifications(owner_email: str, owner_phone: Optional[str], customer_email: str, customer_phone: Optional[str], booking_details: dict, locale: str = 'en'):
    # This is a placeholder. In a real app, you'd load translated strings.
    # For now, using English.
    subject = "New Booking Confirmation"
    owner_html_content = f"""
        <h1>New Booking Received!</h1>
        <p>You have a new booking from {booking_details['customer_name']} for {booking_details['service_name']}.</p>
        <p>Date: {booking_details['booking_date'].strftime('%Y-%m-%d')}</p>
        <p>Time: {booking_details['booking_time']}</p>
        <p>Customer Email: {booking_details['customer_email']}</p>
        <p>Customer Phone: {booking_details['customer_phone'] or 'N/A'}</p>
        <p>Check your dashboard for details.</p>
    """
    customer_html_content = f"""
        <h1>Your Booking is Confirmed!</h1>
        <p>Dear {booking_details['customer_name']},</p>
        <p>Your booking for {booking_details['service_name']} on {booking_details['booking_date'].strftime('%Y-%m-%d')} at {booking_details['booking_time']} has been confirmed.</p>
        <p>We look forward to seeing you!</p>
    """

    send_email(owner_email, subject, owner_html_content)
    send_email(customer_email, subject, customer_html_content)

    if owner_phone:
        owner_whatsapp_msg = f"New booking: {booking_details['customer_name']} for {booking_details['service_name']} on {booking_details['booking_date'].strftime('%Y-%m-%d')} at {booking_details['booking_time']}. Customer: {booking_details['customer_phone'] or booking_details['customer_email']}"
        send_whatsapp_message(owner_phone, owner_whatsapp_msg)

    if customer_phone:
        customer_whatsapp_msg = f"Your booking for {booking_details['service_name']} on {booking_details['booking_date'].strftime('%Y-%m-%d')} at {booking_details['booking_time']} is confirmed!"
        send_whatsapp_message(customer_phone, customer_whatsapp_msg)
