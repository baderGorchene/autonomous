import os
import logging
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from twilio.rest import Client
from jinja2 import Environment, FileSystemLoader
from .config import settings
from . import models, schemas

logger = logging.getLogger(__name__)

# Setup Jinja2 for email templates
TEMPLATES_DIR = os.path.join(settings.PROJECT_ROOT, 'templates')
email_jinja_env = Environment(loader=FileSystemLoader(TEMPLATES_DIR))

def render_email_template(template_name: str, context: dict) -> str:
    template = email_jinja_env.get_template(template_name)
    return template.render(context)

def send_email(to_email: str, subject: str, html_content: str):
    if not settings.SENDGRID_API_KEY:
        logger.warning("SENDGRID_API_KEY is not set. Skipping email sending.")
        return

    message = Mail(
        from_email='noreply@bookslot.app', # Replace with your verified sender
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

def send_whatsapp_message(to_phone_number: str, message_body: str):
    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN or not settings.TWILIO_WHATSAPP_NUMBER:
        logger.warning("Twilio credentials or WhatsApp number not set. Skipping WhatsApp message.")
        return

    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        message = client.messages.create(
            from_=f'whatsapp:{settings.TWILIO_WHATSAPP_NUMBER}',
            body=message_body,
            to=f'whatsapp:{to_phone_number}'
        )
        logger.info(f"WhatsApp message sent to {to_phone_number}. SID: {message.sid}")
    except Exception as e:
        logger.error(f"Error sending WhatsApp message to {to_phone_number}: {e}")

def send_booking_confirmation_email(owner: models.Owner, booking: models.Booking, service: dict):
    subject = f"Your booking with {owner.business_name} is confirmed!"
    context = {
        "owner_name": owner.name,
        "business_name": owner.business_name,
        "customer_name": booking.customer_name,
        "service_name": booking.service_name,
        "booking_date": booking.booking_date.strftime("%Y-%m-%d"),
        "booking_time": booking.booking_time.strftime("%H:%M"),
        "service_duration": service.get('duration', 'N/A'),
        "service_price": service.get('price', 'N/A'),
        "owner_phone": owner.phone,
        "owner_email": owner.email,
    }
    html_content = render_email_template("email_booking_confirmation.html", context)
    send_email(booking.customer_email, subject, html_content)

def send_owner_notification(owner: models.Owner, booking: models.Booking, service: dict):
    subject = f"New Booking for {service['name']} at {owner.business_name}"
    context = {
        "owner_name": owner.name,
        "business_name": owner.business_name,
        "customer_name": booking.customer_name,
        "customer_email": booking.customer_email,
        "customer_phone": booking.customer_phone,
        "service_name": booking.service_name,
        "booking_date": booking.booking_date.strftime("%Y-%m-%d"),
        "booking_time": booking.booking_time.strftime("%H:%M"),
        "service_duration": service.get('duration', 'N/A'),
        "service_price": service.get('price', 'N/A'),
    }
    html_content = render_email_template("email_owner_notification.html", context)
    
    # Send email to owner
    send_email(owner.email, subject, html_content)
    
    # Send WhatsApp notification to owner
    whatsapp_message = (
        f"New Booking for {owner.business_name}:\n"
        f"Service: {booking.service_name}\n"
        f"Date: {booking.booking_date.strftime('%Y-%m-%d')}\n"
        f"Time: {booking.booking_time.strftime('%H:%M')}\n"
        f"Customer: {booking.customer_name} ({booking.customer_phone or booking.customer_email})"
    )
    if owner.phone:
        send_whatsapp_message(owner.phone, whatsapp_message)
    else:
        logger.warning(f"Owner {owner.email} has no phone number for WhatsApp notifications.")
