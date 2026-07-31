import os
import logging
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from twilio.rest import Client
from src.config import settings

logger = logging.getLogger(__name__)

def send_email(to_email: str, subject: str, html_content: str, api_key: str):
    if not api_key:
        logger.warning("SendGrid API key not configured. Email not sent.")
        return

    message = Mail(
        from_email='no-reply@bookslot.app', # Replace with your verified sender email
        to_emails=to_email,
        subject=subject,
        html_content=html_content
    )
    try:
        sendgrid_client = SendGridAPIClient(api_key)
        response = sendgrid_client.send(message)
        logger.info(f"Email sent to {to_email}. Status Code: {response.status_code}")
    except Exception as e:
        logger.error(f"Error sending email to {to_email}: {e}", exc_info=True)

def send_whatsapp_message(to_number: str, message_body: str, account_sid: str, auth_token: str, from_whatsapp_number: str):
    if not all([account_sid, auth_token, from_whatsapp_number]):
        logger.warning("Twilio credentials not fully configured. WhatsApp message not sent.")
        return

    try:
        client = Client(account_sid, auth_token)
        message = client.messages.create(
            from_=f'whatsapp:{from_whatsapp_number}',
            body=message_body,
            to=f'whatsapp:{to_number}'
        )
        logger.info(f"WhatsApp message sent to {to_number}. SID: {message.sid}")
    except Exception as e:
        logger.error(f"Error sending WhatsApp message to {to_number}: {e}", exc_info=True)

def send_owner_notification(owner, booking, sendgrid_api_key, twilio_account_sid, twilio_auth_token, twilio_whatsapp_number):
    # Email notification to owner
    email_subject = f"New Booking for {booking.service_name} at {booking.booking_time} on {booking.booking_date}"
    email_html = f"""
    <html><body>
        <p>Dear {owner.name},</p>
        <p>You have a new booking!</p>
        <p><strong>Service:</strong> {booking.service_name}</p>
        <p><strong>Date:</strong> {booking.booking_date.strftime('%Y-%m-%d')}</p>
        <p><strong>Time:</strong> {booking.booking_time.strftime('%H:%M')}</p>
        <p><strong>Customer:</strong> {booking.customer_name}</p>
        <p><strong>Customer Email:</strong> {booking.customer_email}</p>
        <p><strong>Customer Phone:</strong> {booking.customer_phone or 'N/A'}</p>
        <p><strong>Notes:</strong> {booking.notes or 'None'}</p>
        <p>View all bookings on your dashboard: <a href="https://bookslot.app/owner/dashboard">BookSlot Dashboard</a></p>
    </body></html>
    """
    send_email(owner.email, email_subject, email_html, sendgrid_api_key)

    # WhatsApp notification to owner
    if owner.phone:
        whatsapp_message = (
            f"New booking for {owner.business_name}!\n"
            f"Service: {booking.service_name}\n"
            f"Date: {booking.booking_date.strftime('%Y-%m-%d')}\n"
            f"Time: {booking.booking_time.strftime('%H:%M')}\n"
            f"Customer: {booking.customer_name}\n"
            f"Phone: {booking.customer_phone or 'N/A'}"
        )
        send_whatsapp_message(owner.phone, whatsapp_message, twilio_account_sid, twilio_auth_token, twilio_whatsapp_number)

def send_customer_confirmation(owner, booking, sendgrid_api_key):
    # Email confirmation to customer
    email_subject = f"Your Booking Confirmation for {owner.business_name}"
    email_html = f"""
    <html><body>
        <p>Dear {booking.customer_name},</p>
        <p>Thank you for booking with {owner.business_name}!</p>
        <p>Your booking details:</p>
        <p><strong>Service:</strong> {booking.service_name}</p>
        <p><strong>Date:</strong> {booking.booking_date.strftime('%Y-%m-%d')}</p>
        <p><strong>Time:</strong> {booking.booking_time.strftime('%H:%M')}</p>
        <p>We look forward to seeing you!</p>
        <p>If you need to reschedule or cancel, please contact {owner.name} at {owner.email} or {owner.phone or 'their business phone'}.</p>
    </body></html>
    """
    send_email(booking.customer_email, email_subject, email_html, sendgrid_api_key)
