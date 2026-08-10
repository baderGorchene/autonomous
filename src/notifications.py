import os
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from twilio.rest import Client
import logging
from gettext import translation
import os

from . import models
from .config import settings

logger = logging.getLogger(__name__)

LOCALES_DIR = "locales"
DEFAULT_LOCALE = "en"

def _get_translation_function(locale: str):
    try:
        t = translation("messages", LOCALES_DIR, languages=[locale])
        return t.gettext
    except Exception as e:
        logger.error(f"Error loading translation for {locale} in notifications: {e}")
        return lambda x: x 

def send_email(to_email: str, subject: str, html_content: str):
    if not settings.SENDGRID_API_KEY or settings.SENDGRID_API_KEY == "SG....":
        logger.warning("SendGrid API key not configured. Email not sent.")
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

def send_sms(to_phone_number: str, body: str):
    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN or not settings.TWILIO_PHONE_NUMBER:
        logger.warning("Twilio credentials not configured. SMS not sent.")
        return
    
    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        message = client.messages.create(
            to=to_phone_number,
            from_=settings.TWILIO_PHONE_NUMBER,
            body=body
        )
        logger.info(f"SMS sent to {to_phone_number}. SID: {message.sid}")
    except Exception as e:
        logger.error(f"Error sending SMS to {to_phone_number}: {e}")

def send_booking_confirmation_email(owner: models.Owner, service: models.Service, booking: models.Booking, customer: models.Customer, locale: str = DEFAULT_LOCALE):
    _ = _get_translation_function(locale)
    subject = _("Your Booking Confirmation for {service_name}").format(service_name=service.name)
    html_content = f"""
        <html>
            <body>
                <p>{_("Hi {customer_name},").format(customer_name=customer.name)}</p>
                <p>{_("Your booking for {service_name} with {owner_name} has been confirmed!").format(service_name=service.name, owner_name=owner.name)}</p>
                <p>{_("Details:")}</p>
                <ul>
                    <li>{_("Service:")} {service.name}</li>
                    <li>{_("Date:")} {booking.date.strftime('%Y-%m-%d')}</li>
                    <li>{_("Time:")} {booking.time.strftime('%H:%M')}</li>
                    <li>{_("Duration:")} {service.duration_minutes} {_("minutes")}</li>
                    <li>{_("Price:")} {service.price / 100:.2f} {owner.currency}</li>
                </ul>
                <p>{_("We look forward to seeing you!")}</p>
                <p>{_("Best regards,")}</p>
                <p>{owner.name}</p>
            </body>
        </html>
    """
    send_email(customer.email, subject, html_content)

def send_owner_notification(owner: models.Owner, service: models.Service, booking: models.Booking, customer: models.Customer, locale: str = DEFAULT_LOCALE):
    _ = _get_translation_function(locale)
    subject = _("New Booking Received for {service_name}!").format(service_name=service.name)
    html_content = f"""
        <html>
            <body>
                <p>{_("Hi {owner_name},").format(owner_name=owner.name)}</p>
                <p>{_("You have received a new booking for your service: {service_name}").format(service_name=service.name)}</p>
                <p>{_("Booking Details:")}</p>
                <ul>
                    <li>{_("Service:")} {service.name}</li>
                    <li>{_("Date:")} {booking.date.strftime('%Y-%m-%d')}</li>
                    <li>{_("Time:")} {booking.time.strftime('%H:%M')}</li>
                    <li>{_("Customer Name:")} {customer.name}</li>
                    <li>{_("Customer Email:")} {customer.email}</li>
                    <li>{_("Customer Phone:")} {customer.phone or _("N/A")}</li>
                </ul>
                <p>{_("Please check your dashboard for more details.")}</p>
                <p>{_("Best regards,")}</p>
                <p>BookSlot Team</p>
            </body>
        </html>
    """
    send_email(owner.email, subject, html_content)
    if owner.phone:
        sms_body = _("New booking for {service_name} on {date} at {time} by {customer_name}. Check dashboard for details.").format(
            service_name=service.name,
            date=booking.date.strftime('%Y-%m-%d'),
            time=booking.time.strftime('%H:%M'),
            customer_name=customer.name
        )
        send_sms(owner.phone, sms_body)
