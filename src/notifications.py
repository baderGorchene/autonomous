# src/notifications.py
from datetime import datetime
from typing import Optional
from .config import settings
import sendgrid
from sendgrid.helpers.mail import Mail
from twilio.rest import Client
import gettext
import os

def get_locale_dir():
    return settings.LOCALES_DIR

def get_translator(locale: str):
    try:
        return gettext.translation('messages', get_locale_dir(), languages=[locale])
    except FileNotFoundError:
        return gettext.NullTranslations()

def send_email(to_email: str, subject: str, html_content: str):
    if not settings.SENDGRID_API_KEY:
        print(f"SendGrid API Key not set. Skipping email to {to_email} with subject: {subject}")
        return

    sg = sendgrid.SendGridAPIClient(settings.SENDGRID_API_KEY)
    # Using a verified sender email in SendGrid is crucial.
    # For development, you might use a generic email. In production, use your domain's email.
    from_email = "no-reply@bookslot.app" # Replace with your verified sender email
    message = Mail(from_email=from_email, to_emails=to_email, subject=subject, html_content=html_content)
    try:
        response = sg.send(message)
        print(f"Email sent to {to_email}. Status Code: {response.status_code}")
    except Exception as e:
        print(f"Error sending email to {to_email}: {e}")

def send_whatsapp_message(to_phone_number: str, body: str):
    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN or not settings.TWILIO_WHATSAPP_NUMBER:
        print(f"Twilio credentials not fully set. Skipping WhatsApp message to {to_phone_number}.")
        return

    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        message = client.messages.create(
            from_=settings.TWILIO_WHATSAPP_NUMBER,
            body=body,
            to=f"whatsapp:{to_phone_number}"
        )
        print(f"WhatsApp message sent to {to_phone_number}. SID: {message.sid}")
    except Exception as e:
        print(f"Error sending WhatsApp message to {to_phone_number}: {e}")

def send_booking_confirmation_email_to_customer(customer_email: str, owner_name: str, service_name: str, booking_time: datetime, locale: str = 'en'):
    _ = get_translator(locale).gettext
    subject = _("Your Booking with {owner_name} is Confirmed!").format(owner_name=owner_name)
    html_content = f"""
    <html>
    <body>
        <p>{_("Hi {customer_email},").format(customer_email=customer_email)}</p>
        <p>{_("Your booking with {owner_name} for {service_name} on {booking_time} is confirmed.").format(
            owner_name=owner_name, service_name=service_name, booking_time=booking_time.strftime('%Y-%m-%d %H:%M'))}</p>
        <p>{_("Thank you for choosing BookSlot!")}</p>
    </body>
    </html>
    """
    send_email(customer_email, subject, html_content)

def send_booking_notification_to_owner(owner_email: str, owner_phone: Optional[str], customer_name: str, customer_email: str, customer_phone: Optional[str], service_name: str, booking_time: datetime, locale: str = 'en'):
    _ = get_translator(locale).gettext
    subject = _("New Booking Received for {service_name}").format(service_name=service_name)
    email_content = f"""
    <html>
    <body>
        <p>{_("Dear {owner_email},").format(owner_email=owner_email)}</p>
        <p>{_("You have a new booking!")}</p>
        <ul>
            <li><strong>{_("Service:")}</strong> {service_name}</li>
            <li><strong>{_("Time:")}</strong> {booking_time.strftime('%Y-%m-%d %H:%M')}</li>
            <li><strong>{_("Customer Name:")}</strong> {customer_name}</li>
            <li><strong>{_("Customer Email:")}</strong> {customer_email}</li>
            <li><strong>{_("Customer Phone:")}</strong> {customer_phone if customer_phone else _("N/A")}</li>
        </ul>
        <p>{_("BookSlot App")}</p>
    </body>
    </html>
    """
    send_email(owner_email, subject, email_content)

    if owner_phone:
        whatsapp_body = _("New Booking! Service: {service_name}, Time: {booking_time}, Customer: {customer_name}").format(
            service_name=service_name,
            booking_time=booking_time.strftime('%Y-%m-%d %H:%M'),
            customer_name=customer_name
        )
        send_whatsapp_message(owner_phone, whatsapp_body)
