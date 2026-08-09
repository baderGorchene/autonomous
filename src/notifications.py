from . import models, schemas
from .config import settings
from typing import Optional
from gettext import gettext as _
import logging

logger = logging.getLogger(__name__)

def send_email(to_email: str, subject: str, body: str):
    if settings.SENDGRID_API_KEY:
        logger.info(f"SIMULATED EMAIL to {to_email} | Subject: {subject} | Body: {body}")
    else:
        logger.warning(f"SendGrid API Key not set. Email to {to_email} not sent. Subject: {subject}")

def send_whatsapp_message(to_phone_number: str, message_body: str):
    if settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN and settings.TWILIO_WHATSAPP_NUMBER:
        logger.info(f"SIMULATED WHATSAPP to {to_phone_number} | Body: {message_body}")
    else:
        logger.warning(f"Twilio credentials not fully set. WhatsApp to {to_phone_number} not sent. Body: {message_body}")

def send_booking_confirmation(booking: models.Booking, owner: models.Owner, service: models.Service, booking_details_url: str):
    customer_subject = _("Your booking for {service_name} is confirmed!").format(service_name=service.name)
    customer_body = _(
        "Hi {customer_name},\n\n"
        "Your booking for {service_name} on {start_time} with {owner_name} is confirmed.\n"
        "Service: {service_name}\n"
        "Date: {booking_date}\n"
        "Time: {booking_time}\n"
        "Duration: {duration_minutes} minutes\n"
        "Price: {price_amount} {currency}\n"
        "Owner contact: {owner_email} {owner_phone}\n\n"
        "View details: {booking_details_url}\n\n"
        "Thank you!"
    ).format(
        customer_name=booking.customer_name,
        service_name=service.name,
        start_time=booking.start_time.strftime('%Y-%m-%d %H:%M'),
        owner_name=owner.full_name or owner.email,
        booking_date=booking.start_time.strftime('%Y-%m-%d'),
        booking_time=booking.start_time.strftime('%H:%M'),
        duration_minutes=service.duration_minutes,
        price_amount=f"{service.price / 100:.2f}",
        currency=owner.currency,
        owner_email=owner.email,
        owner_phone=owner.phone_number or _("N/A"),
        booking_details_url=booking_details_url
    )
    send_email(booking.customer_email, customer_subject, customer_body)
    
    owner_subject = _("New booking for {service_name} from {customer_name}").format(
        service_name=service.name, customer_name=booking.customer_name
    )
    owner_body = _(
        "Hello {owner_name},\n\n"
        "You have a new booking:\n"
        "Service: {service_name}\n"
        "Customer: {customer_name} ({customer_email} {customer_phone})\n"
        "Date: {booking_date}\n"
        "Time: {booking_time}\n"
        "Duration: {duration_minutes} minutes\n"
        "Price: {price_amount} {currency}\n\n"
        "View all bookings on your dashboard.\n\n"
        "BookSlot Team"
    ).format(
        owner_name=owner.full_name or owner.email,
        service_name=service.name,
        customer_name=booking.customer_name,
        customer_email=booking.customer_email,
        customer_phone=booking.customer_phone or _("N/A"),
        booking_date=booking.start_time.strftime('%Y-%m-%d'),
        booking_time=booking.start_time.strftime('%H:%M'),
        duration_minutes=service.duration_minutes,
        price_amount=f"{service.price / 100:.2f}",
        currency=owner.currency
    )
    send_email(owner.email, owner_subject, owner_body)

    if owner.phone_number:
        whatsapp_message = _(
            "New BookSlot booking for {service_name} from {customer_name} on {booking_date} at {booking_time}. "
            "Customer: {customer_phone}. View dashboard for details."
        ).format(
            service_name=service.name,
            customer_name=booking.customer_name,
            booking_date=booking.start_time.strftime('%Y-%m-%d'),
            booking_time=booking.start_time.strftime('%H:%M'),
            customer_phone=booking.customer_phone or _("N/A")
        )
        send_whatsapp_message(owner.phone_number, whatsapp_message)
