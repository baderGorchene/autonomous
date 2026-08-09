from typing import TYPE_CHECKING
from .config import settings
import logging

# Placeholder for actual SendGrid/Twilio integration
# from sendgrid import SendGridAPIClient
# from sendgrid.helpers.mail import Mail
# from twilio.rest import Client

if TYPE_CHECKING:
    from . import models, schemas # Avoid circular imports at runtime

logger = logging.getLogger(__name__)

# Internationalization placeholder (would use gettext from main.py's request context)
def _(text: str, lang: str = "en"): # Simplified for background tasks where request context is not available
    # In a real scenario, for background tasks, you might pass the gettext function or
    # ensure translations are loaded in the task's context.
    # For now, it's a simple passthrough.
    return text

async def send_email(to_email: str, subject: str, body: str, lang: str = "en"):
    logger.info(f"Sending email to {to_email} (lang: {lang}): Subject='{subject}', Body='{body}'")
    # if settings.SENDGRID_API_KEY:
    #     try:
    #         sg = SendGridAPIClient(settings.SENDGRID_API_KEY)
    #         message = Mail(
    #             from_email='noreply@bookslot.app',
    #             to_emails=to_email,
    #             subject=subject,
    #             html_content=body
    #         )
    #         response = sg.send(message)
    #         logger.info(f"Email sent. Status Code: {response.status_code}")
    #     except Exception as e:
    #         logger.error(f"Error sending email: {e}")
    # else:
    #     logger.warning("SENDGRID_API_KEY not set. Email not sent.")

async def send_whatsapp_message(to_number: str, message: str, lang: str = "en"):
    logger.info(f"Sending WhatsApp to {to_number} (lang: {lang}): Message='{message}'")
    # if settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN and settings.TWILIO_WHATSAPP_NUMBER:
    #     try:
    #         client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
    #         message = client.messages.create(
    #             from_=settings.TWILIO_WHATSAPP_NUMBER,
    #             body=message,
    #             to=to_number
    #         )
    #         logger.info(f"WhatsApp message sent. SID: {message.sid}")
    #     except Exception as e:
    #         logger.error(f"Error sending WhatsApp message: {e}")
    # else:
    #     logger.warning("Twilio credentials not fully set. WhatsApp message not sent.")

async def send_booking_confirmation_email(booking: "models.Booking", service: "models.Service", lang: str = "en"):
    subject = _("Your Booking Confirmation for {service_name}", lang=lang).format(service_name=service.name)
    body = _("Hi {customer_name}, your booking for {service_name} at {start_time} on {start_date} is confirmed.", lang=lang).format(
        customer_name=booking.customer_name,
        service_name=service.name,
        start_time=booking.start_time.strftime("%H:%M"),
        start_date=booking.start_time.strftime("%Y-%m-%d")
    )
    await send_email(booking.customer_email, subject, body, lang)

async def send_owner_notification_email(booking: "models.Booking", service: "models.Service", lang: str = "en"):
    subject = _("New Booking for {service_name}", lang=lang).format(service_name=service.name)
    body = _("You have a new booking from {customer_name} for {service_name} at {start_time} on {start_date}.", lang=lang).format(
        customer_name=booking.customer_name,
        service_name=service.name,
        start_time=booking.start_time.strftime("%H:%M"),
        start_date=booking.start_time.strftime("%Y-%m-%d")
    )
    await send_email(service.owner.email, subject, body, lang) # Assuming owner email exists

async def send_owner_notification_whatsapp(booking: "models.Booking", service: "models.Service", lang: str = "en"):
    message = _("New BookSlot booking! {customer_name} for {service_name} on {start_date} at {start_time}.", lang=lang).format(
        customer_name=booking.customer_name,
        service_name=service.name,
        start_date=booking.start_time.strftime("%Y-%m-%d"),
        start_time=booking.start_time.strftime("%H:%M")
    )
    await send_whatsapp_message(service.owner.owner_phone, message, lang)

async def send_customer_notification_whatsapp(booking: "models.Booking", service: "models.Service", lang: str = "en"):
    message = _("Hi {customer_name}, your BookSlot booking for {service_name} on {start_date} at {start_time} is confirmed!", lang=lang).format(
        customer_name=booking.customer_name,
        service_name=service.name,
        start_date=booking.start_time.strftime("%Y-%m-%d"),
        start_time=booking.start_time.strftime("%H:%M")
    )
    await send_whatsapp_message(booking.customer_phone, message, lang)
