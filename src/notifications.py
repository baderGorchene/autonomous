from datetime import date, time
from typing import Optional
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from twilio.rest import Client
import logging

from .config import settings

logger = logging.getLogger(__name__)

def send_email(to_email: str, subject: str, html_content: str):
    """Sends an email using SendGrid."""
    try:
        message = Mail(
            from_email='no-reply@bookslot.app', # Replace with your verified sender
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

def send_whatsapp_message(to_phone_number: str, message_body: str):
    """Sends a WhatsApp message using Twilio."""
    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        message = client.messages.create(
            from_=f"whatsapp:{settings.TWILIO_PHONE_NUMBER}", # Twilio WhatsApp number
            to=f"whatsapp:{to_phone_number}",
            body=message_body
        )
        logger.info(f"WhatsApp message sent to {to_phone_number}. SID: {message.sid}")
        return True
    except Exception as e:
        logger.error(f"Error sending WhatsApp message to {to_phone_number}: {e}")
        return False

def send_booking_confirmation_email(
    customer_email: str,
    owner_email: str,
    owner_name: str,
    service_name: str,
    booking_date: date,
    booking_time: time,
    customer_name: str,
    is_recurring: bool = False
):
    """Sends a booking confirmation email to the customer and owner."""
    date_str = booking_date.strftime("%Y-%m-%d")
    time_str = booking_time.strftime("%H:%M")
    
    recurrence_info = "(Recurring Booking)" if is_recurring else ""

    # To Customer
    customer_subject = f"Booking Confirmation: {service_name} on {date_str} at {time_str} {recurrence_info}"
    customer_html = f"""
    <p>Hi {customer_name},</p>
    <p>Your booking for <strong>{service_name}</strong> with {owner_name} is confirmed!</p>
    <p><strong>Date:</strong> {date_str}</p>
    <p><strong>Time:</strong> {time_str}</p>
    <p>We look forward to seeing you. {recurrence_info}</p>
    <p>Best regards,<br>BookSlot Team</p>
    """
    send_email(customer_email, customer_subject, customer_html)

    # To Owner
    owner_subject = f"New Booking: {service_name} on {date_str} at {time_str} by {customer_name} {recurrence_info}"
    owner_html = f"""
    <p>Hi {owner_name},</p>
    <p>A new booking has been made for your service <strong>{service_name}</strong>.</p>
    <p><strong>Customer:</strong> {customer_name}</p>
    <p><strong>Email:</strong> {customer_email}</p>
    <p><strong>Date:</strong> {date_str}</p>
    <p><strong>Time:</strong> {time_str}</p>
    <p>This booking is {'' if is_recurring else 'not '}part of a recurring series.</p>
    <p>Best regards,<br>BookSlot Team</p>
    """
    send_email(owner_email, owner_subject, owner_html)

def send_booking_notification_whatsapp(
    owner_phone: str,
    owner_name: str,
    service_name: str,
    booking_date: date,
    booking_time: time,
    customer_name: str,
    customer_phone: Optional[str] = None,
    is_recurring: bool = False
):
    """Sends a WhatsApp notification to the owner about a new booking."""
    date_str = booking_date.strftime("%Y-%m-%d")
    time_str = booking_time.strftime("%H:%M")
    
    recurrence_info = "(Recurring)" if is_recurring else ""

    message_body = (
        f"Hi {owner_name},\n\n"
        f"New booking for *{service_name}* {recurrence_info}!\n"
        f"Customer: {customer_name}\n"
        f"Date: {date_str}\n"
        f"Time: {time_str}\n"
        f"Customer Phone: {customer_phone if customer_phone else 'N/A'}"
    )
    send_whatsapp_message(owner_phone, message_body)
