from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from twilio.rest import Client
from .config import settings
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)

def send_email_confirmation(to_email: str, subject: str, html_content: str):
    try:
        message = Mail(
            from_email='noreply@bookslot.app', # Replace with your verified sender
            to_emails=to_email,
            subject=subject,
            html_content=html_content)
        sendgrid_client = SendGridAPIClient(settings.SENDGRID_API_KEY)
        response = sendgrid_client.send(message)
        logger.info(f"Email sent to {to_email}. Status Code: {response.status_code}")
        return True
    except Exception as e:
        logger.error(f"Error sending email to {to_email}: {e}")
        return False

def send_whatsapp_confirmation(to_phone: str, message_body: str):
    try:
        # Twilio phone numbers are typically in E.164 format, e.g., +12345678900
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        message = client.messages.create(
            from_=f'whatsapp:{settings.TWILIO_WHATSAPP_NUMBER}',
            body=message_body,
            to=f'whatsapp:{to_phone}'
        )
        logger.info(f"WhatsApp message sent to {to_phone}. SID: {message.sid}")
        return True
    except Exception as e:
        logger.error(f"Error sending WhatsApp message to {to_phone}: {e}")
        return False

def generate_booking_confirmation_email(owner_name: str, business_name: str, customer_name: str, service_name: str, booking_date: str, booking_time: str, owner_email: str, customer_email: str, lang: str = 'en') -> Dict[str, str]:
    # This is a placeholder. In a real app, you'd use a Jinja2 template for emails
    # and load translations based on 'lang'.
    # For simplicity, returning basic English content here.
    if lang == 'ar':
        subject = f"تأكيد حجزك مع {business_name}"
        customer_body = f"مرحباً {customer_name}, تم تأكيد حجزك لخدمة {service_name} مع {business_name} في تاريخ {booking_date} الساعة {booking_time}."
        owner_body = f"لديك حجز جديد من {customer_name} لخدمة {service_name} في تاريخ {booking_date} الساعة {booking_time}."
    elif lang == 'fr':
        subject = f"Confirmation de votre réservation avec {business_name}"
        customer_body = f"Bonjour {customer_name}, votre réservation pour le service {service_name} avec {business_name} est confirmée le {booking_date} à {booking_time}."
        owner_body = f"Nouvelle réservation de {customer_name} pour le service {service_name} le {booking_date} à {booking_time}."
    else: # English
        subject = f"Your Booking Confirmation with {business_name}"
        customer_body = f"Hi {customer_name}, your booking for {service_name} with {business_name} on {booking_date} at {booking_time} is confirmed."
        owner_body = f"You have a new booking from {customer_name} for {service_name} on {booking_date} at {booking_time}."
    
    return {
        "customer_subject": subject,
        "customer_html": f"<p>{customer_body}</p><p>Thank you!</p>",
        "owner_subject": f"New Booking for {business_name}",
        "owner_html": f"<p>{owner_body}</p><p>Customer Email: {customer_email}</p>"
    }
