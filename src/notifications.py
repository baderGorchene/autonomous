import os
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from twilio.rest import Client
from src.config import settings
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
        html_content=html_content)
    try:
        sendgrid_client = SendGridAPIClient(settings.SENDGRID_API_KEY)
        response = sendgrid_client.send(message)
        logger.info(f"Email sent to {to_email}. Status Code: {response.status_code}")
    except Exception as e:
        logger.error(f"Error sending email to {to_email}: {e}")

def send_whatsapp_message(to_phone_number: str, message_body: str):
    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN or not settings.TWILIO_WHATSAPP_NUMBER:
        logger.warning("Twilio credentials not configured. WhatsApp message will not be sent.")
        return

    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        message = client.messages.create(
            from_=f'whatsapp:{settings.TWILIO_WHATSAPP_NUMBER}',
            to=f'whatsapp:{to_phone_number}',
            body=message_body
        )
        logger.info(f"WhatsApp message sent to {to_phone_number}. SID: {message.sid}")
    except Exception as e:
        logger.error(f"Error sending WhatsApp message to {to_phone_number}: {e}")

def send_booking_confirmation_emails(owner_email: str, customer_email: str, booking_details: dict, owner_name: str, business_name: str):
    # Email to customer
    customer_subject = f"Your booking with {business_name} is confirmed!"
    customer_html = f"""
    <html>
    <body>
        <p>Dear {booking_details['customer_name']},</p>
        <p>Your booking for '{booking_details['service_name']}' with {business_name} on {booking_details['booking_date']} at {booking_details['booking_time']} is confirmed.</p>
        <p>We look forward to seeing you!</p>
        <p>Best regards,<br>{business_name}</p>
    </body>
    </html>
    """
    send_email(customer_email, customer_subject, customer_html)

    # Email to owner
    owner_subject = f"New booking received for {business_name}!"
    owner_html = f"""
    <html>
    <body>
        <p>Dear {owner_name},</p>
        <p>A new booking has been made:</p>
        <ul>
            <li>Customer Name: {booking_details['customer_name']}</li>
            <li>Customer Email: {booking_details['customer_email']}</li>
            <li>Customer Phone: {booking_details.get('customer_phone', 'N/A')}</li>
            <li>Service: {booking_details['service_name']}</li>
            <li>Date: {booking_details['booking_date']}</li>
            <li>Time: {booking_details['booking_time']}</li>
        </ul>
        <p>Please check your dashboard for more details.</p>
        <p>Best regards,<br>BookSlot Team</p>
    </body>
    </html>
    """
    send_email(owner_email, owner_subject, owner_html)

def send_booking_confirmation_whatsapp(owner_phone: str, customer_phone: str, booking_details: dict, business_name: str):
    # WhatsApp to customer
    if customer_phone:
        customer_msg = f"Hi {booking_details['customer_name']}, your booking for '{booking_details['service_name']}' with {business_name} on {booking_details['booking_date']} at {booking_details['booking_time']} is confirmed!"
        send_whatsapp_message(customer_phone, customer_msg)

    # WhatsApp to owner
    if owner_phone:
        owner_msg = f"New booking for {business_name}: {booking_details['customer_name']} booked '{booking_details['service_name']}' on {booking_details['booking_date']} at {booking_details['booking_time']}. Customer: {booking_details['customer_phone']}"
        send_whatsapp_message(owner_phone, owner_msg)
