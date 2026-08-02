import os
import logging
from typing import Optional
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from twilio.rest import Client
from .config import settings
from .schemas import Booking, Owner

logger = logging.getLogger(__name__)

def send_email(to_email: str, subject: str, html_content: str, from_email: str = "no-reply@bookslot.app"):
    if not settings.SENDGRID_API_KEY:
        logger.warning("SENDGRID_API_KEY is not set. Email will not be sent.")
        return False

    message = Mail(
        from_email=from_email,
        to_emails=to_email,
        subject=subject,
        html_content=html_content
    )
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
        logger.warning("Twilio credentials or WhatsApp number not set. WhatsApp message will not be sent.")
        return False
    
    # Twilio expects phone numbers in E.164 format, e.g., "+1234567890"
    # Ensure the 'to_phone_number' is in the correct format.
    if not to_phone_number.startswith('+'):
        logger.warning(f"Recipient phone number {to_phone_number} is not in E.164 format. Prepending '+'.")
        to_phone_number = '+' + to_phone_number.lstrip('0') # Basic attempt to fix, may need more robust validation

    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        message = client.messages.create(
            from_=f"whatsapp:{settings.TWILIO_WHATSAPP_NUMBER}",
            body=message_body,
            to=f"whatsapp:{to_phone_number}"
        )
        logger.info(f"WhatsApp message sent to {to_phone_number}. SID: {message.sid}")
        return True
    except Exception as e:
        logger.error(f"Error sending WhatsApp message to {to_phone_number}: {e}")
        return False

def notify_owner_of_new_booking(owner: Owner, booking: Booking):
    subject = f"New Booking for {owner.business_name}!"
    html_content = f"""
    <html>
        <body>
            <p>Hello {owner.name},</p>
            <p>You have a new booking!</p>
            <ul>
                <li><strong>Customer:</strong> {booking.customer_name}</li>
                <li><strong>Email:</strong> {booking.customer_email}</li>
                <li><strong>Phone:</strong> {booking.customer_phone or 'N/A'}</li>
                <li><strong>Service:</strong> {booking.service_name}</li>
                <li><strong>Date:</strong> {booking.booking_date.strftime('%Y-%m-%d')}</li>
                <li><strong>Time:</strong> {booking.booking_time}</li>
            </ul>
            <p>Thank you!</p>
        </body>
    </html>
    """
    send_email(owner.email, subject, html_content)
    if owner.phone:
        whatsapp_message = (
            f"Hello {owner.name},\n"
            f"You have a new booking from {booking.customer_name} for {booking.service_name} "
            f"on {booking.booking_date.strftime('%Y-%m-%d')} at {booking.booking_time}.\n"
            f"Customer Contact: {booking.customer_email} / {owner.phone or 'N/A'}"
        )
        send_whatsapp_message(owner.phone, whatsapp_message)

def notify_customer_of_booking_confirmation(owner: Owner, booking: Booking):
    subject = f"Your Booking with {owner.business_name} is Confirmed!"
    html_content = f"""
    <html>
        <body>
            <p>Hello {booking.customer_name},</p>
            <p>Your booking with {owner.business_name} has been confirmed!</p>
            <ul>
                <li><strong>Service:</strong> {booking.service_name}</li>
                <li><strong>Date:</strong> {booking.booking_date.strftime('%Y-%m-%d')}</li>
                <li><strong>Time:</strong> {booking.booking_time}</li>
                <li><strong>Business:</strong> {owner.business_name}</li>
                <li><strong>Contact:</strong> {owner.email} / {owner.phone or 'N/A'}</li>
            </ul>
            <p>We look forward to seeing you!</p>
        </body>
    </html>
    """
    send_email(booking.customer_email, subject, html_content)
    if booking.customer_phone:
        whatsapp_message = (
            f"Hello {booking.customer_name},\n"
            f"Your booking with {owner.business_name} for {booking.service_name} "
            f"on {booking.booking_date.strftime('%Y-%m-%d')} at {booking.booking_time} is confirmed.\n"
            f"Contact {owner.business_name}: {owner.email} / {owner.phone or 'N/A'}"
        )
        send_whatsapp_message(booking.customer_phone, whatsapp_message)