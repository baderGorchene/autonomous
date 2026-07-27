import os
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from twilio.rest import Client
from jinja2 import Environment, FileSystemLoader
import gettext
import json

from .config import settings
from . import models, schemas

current_file_dir = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(current_file_dir, os.pardir))
TEMPLATES_DIR = os.path.join(PROJECT_ROOT, 'templates')
LOCALES_DIR = os.path.join(PROJECT_ROOT, 'locales')

def get_email_jinja_env(locale='en'):
    env = Environment(loader=FileSystemLoader(TEMPLATES_DIR), extensions=['jinja2.ext.i18n'])
    
    if not os.path.exists(LOCALES_DIR):
        print(f"Warning: Locales directory not found at {LOCALES_DIR} for email templates.")
        translate = gettext.NullTranslations()
    else:
        try:
            translate = gettext.translation('messages', LOCALES_DIR, languages=[locale], fallback=True)
        except Exception as e:
            print(f"Warning: Could not load translations for email locale '{locale}': {e}")
            translate = gettext.NullTranslations()
            
    env.install_gettext_translations(translate)
    return env

def send_email(to_email: str, subject: str, html_content: str):
    if not settings.SENDGRID_API_KEY:
        print("SendGrid API key not configured. Skipping email.")
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
        print(f"Email sent to {to_email}. Status Code: {response.status_code}")
    except Exception as e:
        print(f"Error sending email to {to_email}: {e}")

def send_whatsapp_message(to_phone_number: str, message_body: str):
    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN or not settings.TWILIO_WHATSAPP_NUMBER:
        print("Twilio credentials not fully configured. Skipping WhatsApp message.")
        return
    
    if not to_phone_number.startswith('+'):
        print(f"Warning: WhatsApp number {to_phone_number} does not start with '+'. Attempting to prepend '+'.")
        to_phone_number = '+' + to_phone_number.lstrip('0')

    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        message = client.messages.create(
            from_=f'whatsapp:{settings.TWILIO_WHATSAPP_NUMBER}',
            body=message_body,
            to=f'whatsapp:{to_phone_number}'
        )
        print(f"WhatsApp message sent to {to_phone_number}. SID: {message.sid}")
    except Exception as e:
        print(f"Error sending WhatsApp message to {to_phone_number}: {e}")

def send_owner_notification(owner: models.Owner, booking: models.Booking, locale: str = 'en'):
    templates = get_email_jinja_env(locale)
    template = templates.get_template("email/owner_notification.html")
    
    services = json.loads(owner.services_json) if owner.services_json else []
    service_details = next((s for s in services if s.get('name') == booking.service_name), {'description': ''})

    html_content = template.render(
        owner=owner,
        booking=booking,
        service_details=service_details,
        booking_time_str=booking.booking_time.strftime("%Y-%m-%d %H:%M")
    )
    
    _ = templates.get_translations().gettext
    subject = _("New Booking Received for %(service_name)s!", service_name=booking.service_name)
    
    send_email(owner.email, subject, html_content)
    
    if owner.phone:
        whatsapp_body = _("Hello %(owner_name)s, you have a new booking for %(service_name)s at %(booking_time_str)s with %(customer_name)s (%(customer_phone)s).",
                          owner_name=owner.name,
                          service_name=booking.service_name,
                          booking_time_str=booking.booking_time.strftime("%Y-%m-%d %H:%M"),
                          customer_name=booking.customer_name,
                          customer_phone=booking.customer_phone or "N/A")
        send_whatsapp_message(owner.phone, whatsapp_body)

def send_customer_confirmation(owner: models.Owner, booking: models.Booking, locale: str = 'en'):
    templates = get_email_jinja_env(locale)
    template = templates.get_template("email/customer_confirmation.html")
    
    services = json.loads(owner.services_json) if owner.services_json else []
    service_details = next((s for s in services if s.get('name') == booking.service_name), {'description': ''})

    html_content = template.render(
        owner=owner,
        booking=booking,
        service_details=service_details,
        booking_time_str=booking.booking_time.strftime("%Y-%m-%d %H:%M")
    )
    
    _ = templates.get_translations().gettext
    subject = _("Your Booking for %(service_name)s is Confirmed!", service_name=booking.service_name)
    
    send_email(booking.customer_email, subject, html_content)
    
    if booking.customer_phone:
        whatsapp_body = _("Hi %(customer_name)s, your booking for %(service_name)s with %(business_name)s is confirmed for %(booking_time_str)s. See you then!",
                          customer_name=booking.customer_name,
                          service_name=booking.service_name,
                          business_name=owner.business_name,
                          booking_time_str=booking.booking_time.strftime("%Y-%m-%d %H:%M"))
        send_whatsapp_message(booking.customer_phone, whatsapp_body)
