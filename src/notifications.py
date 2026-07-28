import os
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from twilio.rest import Client
from .config import settings
import gettext
import os

# Set up locale for notifications
# Assuming notifications.py is in src/, PROJECT_ROOT is one level up
_current_file_dir = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(_current_file_dir, os.pardir))
LOCALES_DIR = os.path.join(PROJECT_ROOT, 'locales')

def _get_translator(locale='en'):
    try:
        # Ensure the locale directory exists before trying to load translations
        if not os.path.exists(LOCALES_DIR):
            print(f"Warning: Locales directory not found at {LOCALES_DIR} for notifications.")
            return gettext.NullTranslations() # Fallback
        
        return gettext.translation('messages', LOCALES_DIR, languages=[locale], fallback=True)
    except Exception as e:
        print(f"Warning: Could not load translations for locale '{locale}' in notifications: {e}")
        return gettext.NullTranslations() # Fallback

def send_booking_confirmation_email(
    owner_email: str,
    customer_email: str,
    owner_name: str,
    customer_name: str,
    service_name: str,
    booking_date: str,
    booking_time: str,
    customer_phone: str,
    locale: str = 'en'
):
    _ = _get_translator(locale).gettext

    # Email to customer
    customer_subject = _("Your Booking with {} is Confirmed!").format(owner_name)
    customer_body = _("""
        Dear {customer_name},

        Your booking for {service_name} with {owner_name} on {booking_date} at {booking_time} has been confirmed.

        We look forward to seeing you!

        Best regards,
        The BookSlot Team
    """).format(
        customer_name=customer_name,
        service_name=service_name,
        owner_name=owner_name,
        booking_date=booking_date,
        booking_time=booking_time
    )
    message_to_customer = Mail(
        from_email=os.getenv('SENDGRID_SENDER_EMAIL', 'noreply@bookslot.app'), # Use an actual sender email
        to_emails=customer_email,
        subject=customer_subject,
        html_content=f"<p>{customer_body.replace(os.linesep, '<br>')}</p>"
    )

    # Email to owner
    owner_subject = _("New Booking Received: {service_name} for {customer_name}").format(
        service_name=service_name,
        customer_name=customer_name
    )
    owner_body = _("""
        Dear {owner_name},

        You have received a new booking:
        Service: {service_name}
        Customer: {customer_name}
        Customer Email: {customer_email}
        Customer Phone: {customer_phone}
        Date: {booking_date}
        Time: {booking_time}

        Please prepare for the appointment.

        Best regards,
        The BookSlot Team
    """).format(
        owner_name=owner_name,
        service_name=service_name,
        customer_name=customer_name,
        customer_email=customer_email,
        customer_phone=customer_phone,
        booking_date=booking_date,
        booking_time=booking_time
    )
    message_to_owner = Mail(
        from_email=os.getenv('SENDGRID_SENDER_EMAIL', 'noreply@bookslot.app'),
        to_emails=owner_email,
        subject=owner_subject,
        html_content=f"<p>{owner_body.replace(os.linesep, '<br>')}</p>"
    )

    try:
        sg = SendGridAPIClient(settings.SENDGRID_API_KEY)
        sg.send(message_to_customer)
        sg.send(message_to_owner)
        print("Emails sent successfully.")
    except Exception as e:
        print(f"Error sending email: {e}")
        # In a real app, you'd log this or use a retry mechanism

def send_whatsapp_notification(
    owner_phone: str,
    customer_name: str,
    service_name: str,
    booking_date: str,
    booking_time: str,
    locale: str = 'en'
):
    _ = _get_translator(locale).gettext
    
    # Twilio requires phone numbers to be in E.164 format (e.g., +12345678900)
    # This example assumes owner_phone is already in or can be converted to E.164
    # In a real app, robust phone number validation/formatting would be needed.

    if not owner_phone:
        print("Warning: Owner phone number not provided for WhatsApp notification.")
        return

    # Construct the message for the owner
    whatsapp_message = _("""
        *New Booking Alert!*

        Service: {service_name}
        Customer: {customer_name}
        Date: {booking_date}
        Time: {booking_time}

        Prepare for your appointment!
    """).format(
        service_name=service_name,
        customer_name=customer_name,
        booking_date=booking_date,
        booking_time=booking_time
    )

    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        message = client.messages.create(
            from_=f"whatsapp:{settings.TWILIO_WHATSAPP_NUMBER}", # Your Twilio WhatsApp number
            to=f"whatsapp:{owner_phone}", # Owner's WhatsApp number
            body=whatsapp_message
        )
        print(f"WhatsApp message sent: {message.sid}")
    except Exception as e:
        print(f"Error sending WhatsApp message: {e}")
        # In a real app, log this error or use a retry mechanism