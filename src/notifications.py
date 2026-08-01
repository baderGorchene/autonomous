import os
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from twilio.rest import Client
import logging
from .config import settings

logger = logging.getLogger(__name__)

def send_email(to_email: str, subject: str, html_content: str):
    if not settings.SENDGRID_API_KEY:
        logger.warning("SendGrid API key not set. Skipping email sending.")
        logger.info(f"Simulated email to {to_email} with subject '{subject}': {html_content[:100]}...")
        return False
    
    try:
        message = Mail(
            from_email='no-reply@bookslot.app', # Replace with your verified sender email
            to_emails=to_email,
            subject=subject,
            html_content=html_content)
        sendgrid_client = SendGridAPIClient(settings.SENDGRID_API_KEY)
        response = sendgrid_client.send(message)
        logger.info(f"Email sent to {to_email}. Status Code: {response.status_code}")
        return True
    except Exception as e:
        logger.error(f"Error sending email to {to_email}: {e}")
        return False

def send_whatsapp_message(to_phone: str, message_body: str):
    if not all([settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN, settings.TWILIO_WHATSAPP_NUMBER]):
        logger.warning("Twilio credentials not fully set. Skipping WhatsApp message sending.")
        logger.info(f"Simulated WhatsApp to {to_phone}: {message_body[:100]}...")
        return False
    
    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        # Twilio requires phone numbers in E.164 format, e.g., "+1234567890"
        # Ensure 'to_phone' is correctly formatted, adding '+' if missing
        if not to_phone.startswith('+'):
            to_phone = f"+{to_phone}"

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

def send_booking_confirmation_email(owner_email: str, customer_email: str, booking_details: dict, owner_name: str, customer_name: str):
    subject_owner = f"New Booking for {booking_details['service_name']} at {booking_details['booking_date']} {booking_details['booking_time']}"
    html_content_owner = f"""
    <p>Hello {owner_name},</p>
    <p>You have a new booking!</p>
    <ul>
        <li>Service: {booking_details['service_name']}</li>
        <li>Date: {booking_details['booking_date']}</li>
        <li>Time: {booking_details['booking_time']}</li>
        <li>Customer: {customer_name} ({customer_email})</li>
        <li>Customer Phone: {booking_details.get('customer_phone', 'N/A')}</li>
    </ul>
    <p>Thank you for using BookSlot!</p>
    """
    send_email(owner_email, subject_owner, html_content_owner)

    subject_customer = f"Your Booking Confirmation for {booking_details['service_name']}"
    html_content_customer = f"""
    <p>Hello {customer_name},</p>
    <p>Your booking has been confirmed!</p>
    <ul>
        <li>Service: {booking_details['service_name']}</li>
        <li>Date: {booking_details['booking_date']}</li>
        <li>Time: {booking_details['booking_time']}</li>
        <li>Business: {owner_name}</li>
    </ul>
    <p>We look forward to seeing you!</p>
    """
    send_email(customer_email, subject_customer, html_content_customer)

def send_booking_whatsapp_notification(owner_phone: str, customer_phone: str, booking_details: dict, owner_name: str, customer_name: str):
    if owner_phone:
        owner_message = (
            f"New Booking for {owner_name}:\n"
            f"Service: {booking_details['service_name']}\n"
            f"Date: {booking_details['booking_date']}\n"
            f"Time: {booking_details['booking_time']}\n"
            f"Customer: {customer_name} ({booking_details['customer_email']})\n"
            f"Customer Phone: {customer_phone if customer_phone else 'N/A'}"
        )
        send_whatsapp_message(owner_phone, owner_message)
    else:
        logger.info("Owner phone not available for WhatsApp notification.")

    if customer_phone:
        customer_message = (
            f"Your booking with {owner_name} is confirmed!\n"
            f"Service: {booking_details['service_name']}\n"
            f"Date: {booking_details['booking_date']}\n"
            f"Time: {booking_details['booking_time']}"
        )
        send_whatsapp_message(customer_phone, customer_message)
    else:
        logger.info("Customer phone not available for WhatsApp notification.")
