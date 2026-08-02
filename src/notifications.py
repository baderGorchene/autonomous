import os
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from twilio.rest import Client
import logging
from .config import settings

logger = logging.getLogger(__name__)

def send_email_notification(to_email: str, subject: str, html_content: str):
    if not settings.SENDGRID_API_KEY:
        logger.warning("SENDGRID_API_KEY is not set. Email notification skipped.")
        return

    message = Mail(
        from_email='no-reply@bookslot.app', # Replace with your verified sender
        to_emails=to_email,
        subject=subject,
        html_content=html_content)
    try:
        sendgrid_client = SendGridAPIClient(settings.SENDGRID_API_KEY)
        response = sendgrid_client.send(message)
        logger.info(f"Email sent to {to_email}. Status Code: {response.status_code}")
    except Exception as e:
        logger.error(f"Error sending email to {to_email}: {e}")

def send_whatsapp_notification(to_phone_number: str, message_body: str):
    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN or not settings.TWILIO_WHATSAPP_NUMBER:
        logger.warning("Twilio credentials or WhatsApp number not set. WhatsApp notification skipped.")
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

def send_booking_confirmation_email(owner_email: str, customer_email: str, booking_details: dict, owner_name: str, business_name: str):
    # For owner
    owner_subject = f"New Booking for {business_name}!"
    owner_html_content = f"""
    <p>Dear {owner_name},</p>
    <p>You have a new booking from {booking_details['customer_name']}:</p>
    <ul>
        <li>Service: {booking_details['service_name']}</li>
        <li>Date: {booking_details['booking_date']}</li>
        <li>Time: {booking_details['booking_time']}</li>
        <li>Customer Email: {booking_details['customer_email']}</li>
        <li>Customer Phone: {booking_details['customer_phone']}</li>
    </ul>
    <p>Thank you!</p>
    """
    send_email_notification(owner_email, owner_subject, owner_html_content)

    # For customer
    customer_subject = f"Your Booking with {business_name} is Confirmed!"
    customer_html_content = f"""
    <p>Dear {booking_details['customer_name']},</p>
    <p>Your booking with {business_name} has been confirmed:</p>
    <ul>
        <li>Service: {booking_details['service_name']}</li>
        <li>Date: {booking_details['booking_date']}</li>
        <li>Time: {booking_details['booking_time']}</li>
    </ul>
    <p>We look forward to seeing you!</p>
    """
    send_email_notification(customer_email, customer_subject, customer_html_content)

def send_booking_confirmation_whatsapp(owner_phone: str, customer_phone: str, booking_details: dict, owner_name: str, business_name: str):
    # For owner
    owner_message = (
        f"New booking for {business_name}! "
        f"Service: {booking_details['service_name']}, "
        f"Date: {booking_details['booking_date']}, "
        f"Time: {booking_details['booking_time']}. "
        f"Customer: {booking_details['customer_name']} ({booking_details['customer_phone']})."
    )
    send_whatsapp_notification(owner_phone, owner_message)

    # For customer
    customer_message = (
        f"Your booking with {business_name} is confirmed! "
        f"Service: {booking_details['service_name']}, "
        f"Date: {booking_details['booking_date']}, "
        f"Time: {booking_details['booking_time']}. "
        f"See you then!"
    )
    send_whatsapp_notification(customer_phone, customer_message)
