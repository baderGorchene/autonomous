import os
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from twilio.rest import Client
from .config import settings
import gettext
from typing import Optional

# Setup gettext for i18n in notifications (outside of request context)
def get_translator(locale: str):
    try:
        if not os.path.exists(os.path.join(settings.LOCALES_DIR, locale, 'LC_MESSAGES', 'messages.mo')):
            raise FileNotFoundError
        t = gettext.translation('messages', settings.LOCALES_DIR, languages=[locale], fallback=True)
    except (FileNotFoundError, gettext.TranslationError):
        t = gettext.translation('messages', settings.LOCALES_DIR, languages=[settings.DEFAULT_LOCALE], fallback=True)
    return t.gettext

async def send_email(to_email: str, subject: str, content: str):
    if not settings.SENDGRID_API_KEY:
        print(f"SendGrid API Key not set. Skipping email to {to_email}: {subject}")
        return

    message = Mail(
        from_email='no-reply@bookslot.app', # Replace with your verified sender email
        to_emails=to_email,
        subject=subject,
        html_content=content
    )
    try:
        sendgrid_client = SendGridAPIClient(settings.SENDGRID_API_KEY)
        response = sendgrid_client.send(message)
        print(f"Email sent to {to_email}. Status Code: {response.status_code}")
    except Exception as e:
        print(f"Error sending email to {to_email}: {e}")

async def send_whatsapp_message(to_phone_number: str, message_body: str):
    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN or not settings.TWILIO_WHATSAPP_NUMBER:
        print(f"Twilio credentials not fully set. Skipping WhatsApp message to {to_phone_number}")
        return

    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        # Twilio requires the 'whatsapp:' prefix for WhatsApp numbers
        message = client.messages.create(
            from_=settings.TWILIO_WHATSAPP_NUMBER,
            body=message_body,
            to=f"whatsapp:{to_phone_number}"
        )
        print(f"WhatsApp message sent to {to_phone_number}. SID: {message.sid}")
    except Exception as e:
        print(f"Error sending WhatsApp message to {to_phone_number}: {e}")

async def send_booking_confirmation_emails(
    owner_email: str,
    customer_email: str,
    owner_name: str,
    customer_name: str,
    service_name: str,
    booking_time: str,
    owner_phone: Optional[str] = None,
    customer_phone: Optional[str] = None,
    locale: str = "en"
):
    _ = get_translator(locale)

    # Owner Notification
    owner_subject = _("New Booking Confirmation for {service_name}").format(service_name=service_name)
    owner_content = _("""
        <p>Dear {owner_name},</p>
        <p>You have a new booking!</p>
        <ul>
            <li><strong>Service:</strong> {service_name}</li>
            <li><strong>Customer:</strong> {customer_name}</li>
            <li><strong>Customer Email:</strong> {customer_email}</li>
            <li><strong>Customer Phone:</strong> {customer_phone}</li>
            <li><strong>Booking Time:</strong> {booking_time}</li>
        </ul>
        <p>Thank you!</p>
        <p>BookSlot Team</p>
    """).format(
        owner_name=owner_name,
        service_name=service_name,
        customer_name=customer_name,
        customer_email=customer_email,
        customer_phone=customer_phone if customer_phone else _("N/A"),
        booking_time=booking_time
    )
    await send_email(owner_email, owner_subject, owner_content)

    # Customer Notification
    customer_subject = _("Your Booking Confirmation for {service_name}").format(service_name=service_name)
    customer_content = _("""
        <p>Dear {customer_name},</p>
        <p>Your booking for <strong>{service_name}</strong> has been confirmed!</p>
        <ul>
            <li><strong>Service:</strong> {service_name}</li>
            <li><strong>With:</strong> {owner_name}</li>
            <li><strong>Your Booking Time:</strong> {booking_time}</li>
            <li><strong>Owner Contact:</strong> {owner_phone}</li>
        </ul>
        <p>We look forward to seeing you!</p>
        <p>BookSlot Team</p>
    """).format(
        customer_name=customer_name,
        service_name=service_name,
        owner_name=owner_name,
        booking_time=booking_time,
        owner_phone=owner_phone if owner_phone else _("N/A")
    )
    await send_email(customer_email, customer_subject, customer_content)

    # Owner WhatsApp Notification (optional)
    if owner_phone:
        whatsapp_owner_message = _("New booking for {service_name} with {customer_name} at {booking_time}. Customer contact: {customer_phone}").format(
            service_name=service_name,
            customer_name=customer_name,
            booking_time=booking_time,
            customer_phone=customer_phone if customer_phone else _("N/A")
        )
        await send_whatsapp_message(owner_phone, whatsapp_owner_message)
