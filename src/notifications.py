import os
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from twilio.rest import Client
import logging
from src.config import settings
from src import schemas

logger = logging.getLogger(__name__)

# --- Email Notifications (SendGrid) ---
def send_email_notification(to_email: str, subject: str, html_content: str):
    if not settings.SENDGRID_API_KEY:
        logger.warning("SendGrid API key not configured. Skipping email notification.")
        return

    message = Mail(
        from_email='no-reply@bookslot.app',
        to_emails=to_email,
        subject=subject,
        html_content=html_content
    )
    try:
        sendgrid_client = SendGridAPIClient(settings.SENDGRID_API_KEY)
        response = sendgrid_client.send(message)
        logger.info(f"Email sent to {to_email}. Status Code: {response.status_code}")
    except Exception as e:
        logger.error(f"Error sending email to {to_email}: {e}")

def send_booking_confirmation_emails(owner_email: str, customer_email: str, booking: schemas.Booking, owner_name: str, business_name: str, customer_name: str, booking_page_link: str):
    customer_subject = f"Your booking with {business_name} is confirmed!"
    customer_html = f"""
    <p>Hi {customer_name},</p>
    <p>Your booking for <b>{booking.service_name}</b> with {business_name} on <b>{booking.booking_date.strftime('%Y-%m-%d')}</b> at <b>{booking.booking_time}</b> is confirmed.</p>
    <p>We look forward to seeing you!</p>
    <p>Best regards,<br>{business_name}</p>
    """
    send_email_notification(customer_email, customer_subject, customer_html)

    owner_subject = f"New Booking for {business_name}!"
    owner_html = f"""
    <p>Hi {owner_name},</p>
    <p>A new booking has been made for <b>{booking.service_name}</b>.</p>
    <ul>
        <li><b>Customer:</b> {customer_name}</li>
        <li><b>Email:</b> {customer_email}</li>
        <li><b>Phone:</b> {booking.customer_phone or 'N/A'}</li>
        <li><b>Date:</b> {booking.booking_date.strftime('%Y-%m-%d')}</li>
        <li><b>Time:</b> {booking.booking_time}</li>
        <li><b>Message:</b> {booking.message or 'N/A'}</li>
    </ul>
    <p>View all bookings on your dashboard: {booking_page_link}/owner/dashboard</p>
    """
    send_email_notification(owner_email, owner_subject, owner_html)

# --- WhatsApp Notifications (Twilio) ---
def send_whatsapp_notification(to_phone_number: str, message_body: str):
    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN or not settings.TWILIO_WHATSAPP_NUMBER:
        logger.warning("Twilio credentials not fully configured. Skipping WhatsApp notification.")
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

def send_new_booking_whatsapp_notification(owner_phone: str, booking: schemas.Booking, business_name: str, customer_name: str):
    if not owner_phone:
        logger.info(f"Owner phone number not provided for {business_name}. Skipping WhatsApp notification.")
        return

    message_body = (
        f"New booking for {business_name}!\n"
        f"Service: {booking.service_name}\n"
        f"Customer: {customer_name}\n"
        f"Date: {booking.booking_date.strftime('%Y-%m-%d')}\n"
        f"Time: {booking.booking_time}\n"
        f"Contact: {booking.customer_phone or booking.customer_email}"
    )
    send_whatsapp_notification(owner_phone, message_body)
