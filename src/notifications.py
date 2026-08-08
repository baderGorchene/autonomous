from src.config import settings
import smtplib
from email.mime.text import MIMEText
from twilio.rest import Client
import gettext as gt
from typing import Optional

twilio_client: Optional[Client] = None
if settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN:
    try:
        twilio_client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
    except Exception as e:
        print(f"Error initializing Twilio client: {e}")

def get_translation_function(lang: str):
    try:
        locales_dir = settings.LOCALES_DIR
        translation = gt.translation('messages', locales_dir, languages=[lang])
        return translation.gettext
    except Exception as e:
        print(f"Error loading translation for {lang}: {e}")
        return gt.gettext

def send_email(to_email: str, subject: str, body: str):
    if not settings.SENDGRID_API_KEY:
        print(f"Skipping email to {to_email}: SendGrid API key not set. Subject: '{subject}'")
        return
    print(f"--- Sending Email ---")
    print(f"To: {to_email}")
    print(f"Subject: {subject}")
    print(f"Body:\n{body}")
    print(f"---------------------")

def send_whatsapp_message(to_phone: str, body: str):
    if not settings.TWILIO_WHATSAPP_NUMBER or not twilio_client:
        print(f"Skipping WhatsApp to {to_phone}: Twilio credentials or sender number not set. Message: '{body}'")
        return
    
    try:
        message = twilio_client.messages.create(
            from_=settings.TWILIO_WHATSAPP_NUMBER,
            body=body,
            to=f"whatsapp:{to_phone}"
        )
        print(f"WhatsApp message sent to {to_phone} with SID: {message.sid}")
    except Exception as e:
        print(f"Error sending WhatsApp message to {to_phone}: {e}")

def send_booking_confirmation_email(owner_email: str, customer_email: str, booking_details: dict, service_name: str, owner_name: str, lang: str):
    _ = get_translation_function(lang)

    subject = _("Booking Confirmation for {service_name}").format(service_name=service_name)
    body_customer = _("""
        Dear {customer_name},
        Your booking for {service_name} with {owner_name} on {booking_time} has been confirmed.
        Thank you!
    """).format(
        customer_name=booking_details["customer_name"],
        service_name=service_name,
        owner_name=owner_name,
        booking_time=booking_details["booking_time"].strftime('%Y-%m-%d %H:%M')
    )
    send_email(customer_email, subject, body_customer)

    subject_owner = _("New Booking for {service_name}").format(service_name=service_name)
    body_owner = _("""
        Dear {owner_name},
        You have a new booking:
        Service: {service_name}
        Customer: {customer_name} ({customer_email}, {customer_phone})
        Time: {booking_time}
    """).format(
        owner_name=owner_name,
        service_name=service_name,
        customer_name=booking_details["customer_name"],
        customer_email=booking_details["customer_email"],
        customer_phone=booking_details["customer_phone"] or _("N/A"),
        booking_time=booking_details["booking_time"].strftime('%Y-%m-%d %H:%M')
    )
    send_email(owner_email, subject_owner, body_owner)

def send_booking_notification_whatsapp(owner_phone: Optional[str], customer_name: str, booking_details: dict, service_name: str, lang: str):
    if not owner_phone:
        print(f"Skipping WhatsApp notification: Owner phone not provided.")
        return

    _ = get_translation_function(lang)

    message = _("New booking for {service_name} by {customer_name} on {booking_time}.").format(
        service_name=service_name,
        customer_name=customer_name,
        booking_time=booking_details["booking_time"].strftime('%Y-%m-%d %H:%M')
    )
    send_whatsapp_message(owner_phone, message)

def send_premium_welcome_email(owner_email: str, owner_name: str, lang: str):
    _ = get_translation_function(lang)

    subject = _("Welcome to BookSlot Premium, {owner_name}!").format(owner_name=owner_name)
    body = _("""
        Dear {owner_name},
        Thank you for upgrading to BookSlot Premium! You now have unlimited bookings and access to advanced features.
        We're excited to help your business grow.
        Best regards,
        The BookSlot Team
    """).format(owner_name=owner_name)
    send_email(owner_email, subject, body)
