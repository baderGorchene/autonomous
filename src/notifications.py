from .config import settings
from . import models
from typing import Dict, Optional
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from twilio.rest import Client
import logging

logger = logging.getLogger(__name__)

def _(text, locale="en"):
    return text

async def send_email(to_email: str, subject: str, html_content: str):
    if not settings.SENDGRID_API_KEY:
        logger.warning(f"SendGrid API Key not set. Skipping email to {to_email}")
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
        return response
    except Exception as e:
        logger.error(f"Error sending email to {to_email}: {e}")
        raise

async def send_whatsapp_message(to_phone_number: str, message_body: str):
    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN or not settings.TWILIO_WHATSAPP_NUMBER:
        logger.warning(f"Twilio credentials not fully set. Skipping WhatsApp message to {to_phone_number}")
        return

    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        message = client.messages.create(
            from_=settings.TWILIO_WHATSAPP_NUMBER,
            body=message_body,
            to=f"whatsapp:{to_phone_number}"
        )
        logger.info(f"WhatsApp message sent to {to_phone_number}. SID: {message.sid}")
        return message
    except Exception as e:
        logger.error(f"Error sending WhatsApp message to {to_phone_number}: {e}")
        raise

async def send_booking_confirmation_emails(db_booking: models.Booking, owner_email: str, owner_name: str, owner_locale: str):
    customer_subject = str(_("Your booking is confirmed!", owner_locale))
    customer_body = str(_(f"Hi {db_booking.customer_name},\n\nYour booking for {db_booking.service.name} with {owner_name} on {db_booking.start_time.strftime('%Y-%m-%d %H:%M')} is confirmed.", owner_locale))

    owner_subject = str(_("New booking received!", owner_locale))
    owner_body = str(_(f"Hi {owner_name},\n\nYou have a new booking from {db_booking.customer_name} for {db_booking.service.name} on {db_booking.start_time.strftime('%Y-%m-%d %H:%M')}.", owner_locale))

    await send_email(db_booking.customer_email, customer_subject, f"<p>{customer_body}</p>")
    await send_email(owner_email, owner_subject, f"<p>{owner_body}</p>")

async def send_booking_confirmation_whatsapp(db_booking: models.Booking, owner_phone: Optional[str], owner_name: str, owner_locale: str):
    customer_message = str(_(f"Hi {db_booking.customer_name}, your booking for {db_booking.service.name} with {owner_name} on {db_booking.start_time.strftime('%Y-%m-%d %H:%M')} is confirmed.", owner_locale))
    owner_message = str(_(f"Hi {owner_name}, you have a new booking from {db_booking.customer_name} for {db_booking.service.name} on {db_booking.start_time.strftime('%Y-%m-%d %H:%M')}.", owner_locale))

    if db_booking.customer_phone:
        await send_whatsapp_message(db_booking.customer_phone, customer_message)
    if owner_phone:
        await send_whatsapp_message(owner_phone, owner_message)
