import os
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from twilio.rest import Client
import logging

from src.config import settings

logger = logging.getLogger(__name__)

def send_email(to_email: str, subject: str, html_content: str):
    if not settings.SENDGRID_API_KEY:
        logger.warning("SENDGRID_API_KEY is not set. Skipping email sending.")
        return False

    message = Mail(
        from_email='noreply@bookslot.app', # Replace with your verified sender email
        to_emails=to_email,
        subject=subject,
        html_content=html_content)
    try:
        sendgrid_client = SendGridAPIClient(settings.SENDGRID_API_KEY)
        response = sendgrid_client.send(message)
        logger.info(f"Email sent to {to_email}. Status Code: {response.status_code}")
        return True
    except Exception as e:
        logger.error(f"Error sending email to {to_email}: {e}")
        return False

def send_whatsapp_message(to_phone_number: str, message_body: str):
    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN or not settings.TWILIO_WHATSAPP_NUMBER:
        logger.warning("Twilio credentials or WhatsApp number not set. Skipping WhatsApp message.")
        return False

    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        message = client.messages.create(
            from_=f'whatsapp:{settings.TWILIO_WHATSAPP_NUMBER}',
            body=message_body,
            to=f'whatsapp:{to_phone_number}'
        )
        logger.info(f"WhatsApp message sent to {to_phone_number}. SID: {message.sid}")
        return True
    except Exception as e:
        logger.error(f"Error sending WhatsApp message to {to_phone_number}: {e}")
        return False

def send_booking_confirmation_to_customer(booking_details: dict, owner_details: dict):
    subject = f"Your booking with {owner_details['business_name']} is confirmed!"
    html_content = f"""
    <p>Dear {booking_details['customer_name']},</p>
    <p>Your booking for '{booking_details['service_name']}' with {owner_details['business_name']} has been confirmed.</p>
    <p>Details:</p>
    <ul>
        <li>Service: {booking_details['service_name']}</li>
        <li>Date: {booking_details['booking_date']}</li>
        <li>Time: {booking_details['booking_time']}</li>
        <li>Business: {owner_details['business_name']}</li>
    </ul>
    <p>We look forward to seeing you!</p>
    """
    send_email(booking_details['customer_email'], subject, html_content)
    if booking_details.get('customer_phone'):
        whatsapp_message = f"Hello {booking_details['customer_name']}, your booking for '{booking_details['service_name']}' with {owner_details['business_name']} on {booking_details['booking_date']} at {booking_details['booking_time']} is confirmed."
        send_whatsapp_message(booking_details['customer_phone'], whatsapp_message)

def send_new_booking_notification_to_owner(booking_details: dict, owner_details: dict):
    subject = f"New booking for {booking_details['service_name']}!"
    html_content = f"""
    <p>Dear {owner_details['name']},</p>
    <p>You have a new booking!</p>
    <p>Details:</p>
    <ul>
        <li>Service: {booking_details['service_name']}</li>
        <li>Date: {booking_details['booking_date']}</li>
        <li>Time: {booking_details['booking_time']}</li>
        <li>Customer Name: {booking_details['customer_name']}</li>
        <li>Customer Email: {booking_details['customer_email']}</li>
        <li>Customer Phone: {booking_details.get('customer_phone', 'N/A')}</li>
    </ul>
    <p>Please check your dashboard for more details.</p>
    """
    send_email(owner_details['email'], subject, html_content)
    if owner_details.get('phone'):
        whatsapp_message = f"New booking from {booking_details['customer_name']} for {booking_details['service_name']} on {booking_details['booking_date']} at {booking_details['booking_time']}."
        send_whatsapp_message(owner_details['phone'], whatsapp_message)
