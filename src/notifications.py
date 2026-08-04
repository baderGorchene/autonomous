from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from twilio.rest import Client
from src.config import settings
import logging
from typing import Dict, Any, Optional
import datetime

logger = logging.getLogger(__name__)

def send_email_notification(to_email: str, subject: str, html_content: str) -> bool:
    if not settings.SENDGRID_API_KEY:
        logger.warning("SendGrid API Key not configured. Skipping email notification.")
        return False

    message = Mail(
        from_email='no-reply@bookslot.app', # Replace with your verified sender email
        to_emails=to_email,
        subject=subject,
        html_content=html_content)
    try:
        sendgrid_client = SendGridAPIClient(settings.SENDGRID_API_KEY)
        response = sendgrid_client.send(message)
        logger.info(f"Email sent to {to_email}. Status Code: {response.status_code}")
        return response.status_code == 202
    except Exception as e:
        logger.error(f"Error sending email to {to_email}: {e}")
        return False

def send_whatsapp_notification(to_phone: str, message_body: str) -> bool:
    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN or not settings.TWILIO_WHATSAPP_NUMBER:
        logger.warning("Twilio credentials not fully configured. Skipping WhatsApp notification.")
        return False

    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        message = client.messages.create(
            from_=settings.TWILIO_WHATSAPP_NUMBER,
            body=message_body,
            to=f"whatsapp:{to_phone}"
        )
        logger.info(f"WhatsApp message sent to {to_phone}. SID: {message.sid}")
        return True
    except Exception as e:
        logger.error(f"Error sending WhatsApp message to {to_phone}: {e}")
        return False

def send_booking_confirmation_email(booking_details: Dict[str, Any], owner_name: str, owner_slug: str, locale: str = 'en'):
    from src.i18n import _ # Import here to avoid circular dependency

    subject = _("Your booking with {} is confirmed!").format(owner_name, locale_code=locale)
    booking_date_str = booking_details["booking_date"].strftime("%Y-%m-%d") if isinstance(booking_details["booking_date"], datetime.date) else str(booking_details["booking_date"])
    
    html_content = _("""
        <p>Dear {customer_name},</p>
        <p>Your booking for <b>{service_name}</b> with {owner_name} has been confirmed!</p>
        <p><b>Date:</b> {booking_date}</p>
        <p><b>Time:</b> {booking_time}</p>
        <p>We look forward to seeing you.</p>
        <p>Best regards,<br>The {owner_name} Team</p>
        <p><small>Powered by BookSlot.app</small></p>
    """).format(
        customer_name=booking_details["customer_name"],
        service_name=booking_details["service_name"],
        owner_name=owner_name,
        booking_date=booking_date_str,
        booking_time=booking_details["booking_time"],
        locale_code=locale
    )
    send_email_notification(booking_details["customer_email"], subject, html_content)

def send_booking_notification_to_owner(booking_details: Dict[str, Any], owner_email: str, owner_phone: Optional[str], owner_name: str, locale: str = 'en'):
    from src.i18n import _ # Import here to avoid circular dependency

    subject = _("New Booking Received for {}!").format(booking_details["service_name"], locale_code=locale)
    booking_date_str = booking_details["booking_date"].strftime("%Y-%m-%d") if isinstance(booking_details["booking_date"], datetime.date) else str(booking_details["booking_date"])

    email_html_content = _("""
        <p>Dear {owner_name},</p>
        <p>You have received a new booking!</p>
        <p><b>Service:</b> {service_name}</p>
        <p><b>Date:</b> {booking_date}</p>
        <p><b>Time:</b> {booking_time}</p>
        <p><b>Customer:</b> {customer_name}</p>
        <p><b>Customer Email:</b> {customer_email}</p>
        <p><b>Customer Phone:</b> {customer_phone}</p>
        <p><small>Powered by BookSlot.app</small></p>
    """).format(
        owner_name=owner_name,
        service_name=booking_details["service_name"],
        booking_date=booking_date_str,
        booking_time=booking_details["booking_time"],
        customer_name=booking_details["customer_name"],
        customer_email=booking_details["customer_email"],
        customer_phone=booking_details["customer_phone"] or _("N/A", locale_code=locale),
        locale_code=locale
    )
    send_email_notification(owner_email, subject, email_html_content)

    if owner_phone:
        whatsapp_message_body = _("""
            New Booking!
            Service: {service_name}
            Date: {booking_date}
            Time: {booking_time}
            Customer: {customer_name}
            Email: {customer_email}
            Phone: {customer_phone}
        """).format(
            service_name=booking_details["service_name"],
            booking_date=booking_date_str,
            booking_time=booking_details["booking_time"],
            customer_name=booking_details["customer_name"],
            customer_email=booking_details["customer_email"],
            customer_phone=booking_details["customer_phone"] or _("N/A", locale_code=locale),
            locale_code=locale
        )
        send_whatsapp_notification(owner_phone, whatsapp_message_body)