import os
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from twilio.rest import Client
import logging
from .config import settings
from .schemas import BookingCreate
from .models import Owner

logger = logging.getLogger(__name__)

def send_email(to_email: str, subject: str, html_content: str):
    if not settings.SENDGRID_API_KEY:
        logger.warning("SENDGRID_API_KEY not set. Skipping email.")
        return False
    
    message = Mail(
        from_email='no-reply@bookslot.app', # Replace with your verified sender
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
        logger.warning("Twilio credentials not fully set. Skipping WhatsApp message.")
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

def send_booking_confirmation_email(owner: Owner, booking: BookingCreate):
    subject = f"Booking Confirmation for {booking.service_name} at {owner.business_name}"
    html_content = f"""
    <html>
    <body>
        <p>Dear {booking.customer_name},</p>
        <p>Your booking for <b>{booking.service_name}</b> at <b>{owner.business_name}</b> has been confirmed.</p>
        <p><b>Date:</b> {booking.booking_date}</p>
        <p><b>Time:</b> {booking.booking_time}</p>
        <p>We look forward to seeing you!</p>
        <p>Best regards,<br>{owner.business_name}</p>
    </body>
    </html>
    """
    send_email(booking.customer_email, subject, html_content)

def send_owner_notification_email(owner: Owner, booking: BookingCreate):
    subject = f"New Booking for {booking.service_name} at {owner.business_name}"
    html_content = f"""
    <html>
    <body>
        <p>Hello {owner.name},</p>
        <p>A new booking has been made:</p>
        <ul>
            <li><b>Customer Name:</b> {booking.customer_name}</li>
            <li><b>Customer Email:</b> {booking.customer_email}</li>
            <li><b>Customer Phone:</b> {booking.customer_phone or 'N/A'}</li>
            <li><b>Service:</b> {booking.service_name}</li>
            <li><b>Date:</b> {booking.booking_date}</li>
            <li><b>Time:</b> {booking.booking_time}</li>
            <li><b>Notes:</b> {booking.notes or 'N/A'}</li>
        </ul>
        <p>Please check your dashboard for more details.</p>
        <p>Best regards,<br>BookSlot Notifications</p>
    </body>
    </html>
    """
    send_email(owner.email, subject, html_content)

def send_owner_notification_whatsapp(owner: Owner, booking: BookingCreate):
    if owner.phone:
        message_body = (
            f"New Booking for {owner.business_name}!\n"
            f"Service: {booking.service_name}\n"
            f"Date: {booking.booking_date}\n"
            f"Time: {booking.booking_time}\n"
            f"Customer: {booking.customer_name} ({booking.customer_phone or booking.customer_email})"
        )
        send_whatsapp_message(owner.phone, message_body)
    else:
        logger.info(f"Owner {owner.email} has no phone number for WhatsApp notifications.")
