import os
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from twilio.rest import Client
from .config import settings
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

def send_email_notification(to_email: str, subject: str, html_content: str):
    """Sends an email using SendGrid."""
    try:
        message = Mail(
            from_email='no-reply@bookslot.app', # This should be a verified sender in SendGrid
            to_emails=to_email,
            subject=subject,
            html_content=html_content
        )
        sendgrid_client = SendGridAPIClient(settings.SENDGRID_API_KEY)
        response = sendgrid_client.send(message)
        logger.info(f"Email sent to {to_email}. Status Code: {response.status_code}")
        return True
    except Exception as e:
        logger.error(f"Error sending email to {to_email}: {e}")
        return False

def send_whatsapp_notification(to_phone_number: str, message_body: str):
    """Sends a WhatsApp message using Twilio."""
    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        # Twilio requires phone numbers in E.164 format (e.g., +1234567890)
        # And for WhatsApp, it typically uses "whatsapp:<number>" format
        to_whatsapp = f"whatsapp:{to_phone_number}"
        from_whatsapp = f"whatsapp:{settings.TWILIO_WHATSAPP_NUMBER}"

        message = client.messages.create(
            from_=from_whatsapp,
            body=message_body,
            to=to_whatsapp
        )
        logger.info(f"WhatsApp message sent to {to_phone_number}. SID: {message.sid}")
        return True
    except Exception as e:
        logger.error(f"Error sending WhatsApp message to {to_phone_number}: {e}")
        return False

def send_booking_confirmation_email(customer_email: str, owner_name: str, service_name: str, booking_datetime: datetime, customer_name: str):
    subject = f"Booking Confirmation for {service_name}"
    html_content = f"""
    <p>Dear {customer_name},</p>
    <p>Your booking for {service_name} with {owner_name} has been confirmed.</p>
    <p>Date and Time: {booking_datetime.strftime('%Y-%m-%d %H:%M')}</p>
    <p>Thank you for choosing BookSlot!</p>
    """
    return send_email_notification(customer_email, subject, html_content)

def send_owner_booking_notification_email(owner_email: str, customer_name: str, customer_phone: str, service_name: str, booking_datetime: datetime):
    subject = f"New Booking Received: {service_name}"
    html_content = f"""
    <p>Dear Owner,</p>
    <p>You have received a new booking!</p>
    <p>Service: {service_name}</p>
    <p>Customer Name: {customer_name}</p>
    <p>Customer Phone: {customer_phone if customer_phone else 'N/A'}</p>
    <p>Date and Time: {booking_datetime.strftime('%Y-%m-%d %H:%M')}</p>
    """
    return send_email_notification(owner_email, subject, html_content)

def send_owner_booking_notification_whatsapp(owner_phone: str, customer_name: str, customer_email: str, service_name: str, booking_datetime: datetime):
    message_body = f"New BookSlot booking: {service_name} for {customer_name} ({customer_email}) on {booking_datetime.strftime('%Y-%m-%d %H:%M')}"
    return send_whatsapp_notification(owner_phone, message_body)