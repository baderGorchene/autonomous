import logging
from . import models
from .config import settings
import sendgrid
from sendgrid.helpers.mail import Mail
from twilio.rest import Client

logger = logging.getLogger(__name__)

def send_email(to_email: str, subject: str, body: str):
    if not settings.SENDGRID_API_KEY:
        logger.warning("SENDGRID_API_KEY is not set. Skipping email notification.")
        return

    try:
        sg = sendgrid.SendGridAPIClient(settings.SENDGRID_API_KEY)
        # Using a placeholder 'from_email' for now. In a real app, this should be configured.
        message = Mail(
            from_email='noreply@bookslot.app',
            to_emails=to_email,
            subject=subject,
            html_content=body
        )
        response = sg.send(message)
        logger.info(f"Email sent to {to_email}. Status Code: {response.status_code}")
    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {e}")

def send_whatsapp_message(to_phone: str, body: str):
    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN or not settings.TWILIO_WHATSAPP_NUMBER:
        logger.warning("Twilio credentials are not fully set. Skipping WhatsApp notification.")
        return

    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        message = client.messages.create(
            from_=f"whatsapp:{settings.TWILIO_WHATSAPP_NUMBER}",
            body=body,
            to=f"whatsapp:{to_phone}"
        )
        logger.info(f"WhatsApp message sent to {to_phone}. SID: {message.sid}")
    except Exception as e:
        logger.error(f"Failed to send WhatsApp message to {to_phone}: {e}")

def send_owner_notification(owner: models.Owner, booking: models.Booking):
    subject = f"New Booking for {owner.business_name}!"
    body = (
        f"Hello {owner.name},\n\n"
        f"You have a new booking!\n\n"
        f"Customer: {booking.customer_name}\n"
        f"Email: {booking.customer_email}\n"
        f"Phone: {booking.customer_phone}\n"
        f"Service: {booking.service_name}\n"
        f"Date: {booking.booking_date.strftime('%Y-%m-%d')}\n"
        f"Time: {booking.booking_time.strftime('%H:%M')}\n\n"
        f"Manage your bookings at your dashboard: bookslot.app/dashboard\n" # Placeholder URL
    )
    send_email(owner.email, subject, body)
    if owner.phone:
        send_whatsapp_message(owner.phone, body)
    logger.info(f"Owner notification sent for booking {booking.id} to {owner.email}.")

def send_customer_confirmation(owner: models.Owner, booking: models.Booking):
    subject = f"Your Booking Confirmation for {owner.business_name}"
    body = (
        f"Hello {booking.customer_name},\n\n"
        f"Your booking with {owner.business_name} has been confirmed!\n\n"
        f"Service: {booking.service_name}\n"
        f"Date: {booking.booking_date.strftime('%Y-%m-%d')}\n"
        f"Time: {booking.booking_time.strftime('%H:%M')}\n\n"
        f"We look forward to seeing you!\n"
        f"Contact {owner.name} at {owner.phone or owner.email} for any questions.\n"
    )
    send_email(booking.customer_email, subject, body)
    if booking.customer_phone:
        send_whatsapp_message(booking.customer_phone, body)
    logger.info(f"Customer confirmation sent for booking {booking.id} to {booking.customer_email}.")
