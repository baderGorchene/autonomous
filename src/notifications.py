import os
import logging
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from twilio.rest import Client
from src.config import settings
from typing import Optional

logger = logging.getLogger(__name__)

# --- Email Notifications (SendGrid) ---
def send_email(to_email: str, subject: str, html_content: str):
    if not settings.SENDGRID_API_KEY:
        logger.warning("SENDGRID_API_KEY is not set. Skipping email.")
        return False
    
    try:
        message = Mail(
            from_email='no-reply@bookslot.app', # Replace with your verified sender email
            to_emails=to_email,
            subject=subject,
            html_content=html_content)
        sg = SendGridAPIClient(settings.SENDGRID_API_KEY)
        response = sg.send(message)
        logger.info(f"Email sent to {to_email}. Status Code: {response.status_code}")
        return True
    except Exception as e:
        logger.error(f"Error sending email to {to_email}: {e}")
        return False

def send_booking_confirmation_email(customer_email: str, owner_email: str, booking_details: dict, owner_name: str, customer_name: str, booking_page_link: str):
    # Customer email
    customer_subject = f"Your booking with {owner_name} is confirmed!"
    customer_html = f"""
    <html>
    <body>
        <p>Hi {customer_name},</p>
        <p>Your booking for <strong>{booking_details['service_name']}</strong> with {owner_name} on <strong>{booking_details['booking_date']}</strong> at <strong>{booking_details['booking_time']}</strong> has been confirmed.</p>
        <p>We look forward to seeing you!</p>
        <p>Book more services here: <a href=\"{booking_page_link}\">{booking_page_link}</a></p>
        <p>Thank you,</p>
        <p>The BookSlot Team</p>
    </body>
    </html>
    """
    send_email(customer_email, customer_subject, customer_html)

    # Owner email
    owner_subject = f"New booking from {customer_name} for {booking_details['service_name']}!"
    owner_html = f"""
    <html>
    <body>
        <p>Hello {owner_name},</p>
        <p>You have a new booking!</p>
        <ul>
            <li><strong>Customer:</strong> {customer_name}</li>
            <li><strong>Email:</strong> {customer_email}</li>
            <li><strong>Phone:</strong> {booking_details.get('customer_phone', 'N/A')}</li>
            <li><strong>Service:</strong> {booking_details['service_name']}</li>
            <li><strong>Date:</strong> {booking_details['booking_date']}</li>
            <li><strong>Time:</strong> {booking_details['booking_time']}</li>
        </ul>
        <p>Manage your bookings: <a href=\"YOUR_DASHBOARD_LINK\">Your Dashboard</a></p>
        <p>Thank you,</p>
        <p>The BookSlot Team</p>
    </body>
    </html>
    """
    send_email(owner_email, owner_subject, owner_html)


# --- WhatsApp Notifications (Twilio) ---
def send_whatsapp_message(to_number: str, message_body: str):
    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN or not settings.TWILIO_WHATSAPP_NUMBER:
        logger.warning("Twilio credentials or WhatsApp number not set. Skipping WhatsApp message.")
        return False

    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        message = client.messages.create(
            from_=f"whatsapp:{settings.TWILIO_WHATSAPP_NUMBER}",
            body=message_body,
            to=f"whatsapp:{to_number}"
        )
        logger.info(f"WhatsApp message sent to {to_number}. SID: {message.sid}")
        return True
    except Exception as e:
        logger.error(f"Error sending WhatsApp message to {to_number}: {e}")
        return False

def send_booking_confirmation_whatsapp(owner_phone: str, customer_phone: Optional[str], booking_details: dict, owner_name: str, customer_name: str):
    # Owner WhatsApp
    if owner_phone:
        owner_message = (
            f"Hello {owner_name},\n"
            f"You have a new booking from {customer_name}!\n"
            f"Service: {booking_details['service_name']}\n"
            f"Date: {booking_details['booking_date']}\n"
            f"Time: {booking_details['booking_time']}\n"
            f"Customer Phone: {customer_phone or 'N/A'}\n"
            f"Customer Email: {booking_details['customer_email']}"
        )
        send_whatsapp_message(owner_phone, owner_message)

    # Customer WhatsApp (optional, if customer_phone is provided and consent obtained)
    if customer_phone:
        customer_message = (
            f"Hi {customer_name},\n"
            f"Your booking for {booking_details['service_name']} with {owner_name} on {booking_details['booking_date']} at {booking_details['booking_time']} has been confirmed!"
        )
        send_whatsapp_message(customer_phone, customer_message)
