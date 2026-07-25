import os
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from twilio.rest import Client
from .config import settings
from jinja2 import Environment, FileSystemLoader
from datetime import datetime

# Determine the base directory of the project
current_file_dir = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(current_file_dir, os.pardir))
TEMPLATES_DIR = os.path.join(PROJECT_ROOT, 'templates')

jinja_env = Environment(loader=FileSystemLoader(TEMPLATES_DIR))

def send_booking_confirmation_email(recipient_email: str, owner_name: str, customer_name: str, service_name: str, booking_time: datetime, is_owner: bool):
    try:
        message_template = jinja_env.get_template('email_confirmation.html')
        
        subject_prefix = "New Booking Confirmation" if is_owner else "Your Booking Confirmation"
        
        html_content = message_template.render(
            owner_name=owner_name,
            customer_name=customer_name,
            service_name=service_name,
            booking_time=booking_time.strftime("%Y-%m-%d %H:%M"),
            is_owner=is_owner
        )

        message = Mail(
            from_email='no-reply@bookslot.app',
            to_emails=recipient_email,
            subject=f"{subject_prefix} for {service_name}",
            html_content=html_content
        )
        sg = SendGridAPIClient(settings.SENDGRID_API_KEY)
        response = sg.send(message)
        print(f"Email sent to {recipient_email}. Status Code: {response.status_code}")
    except Exception as e:
        print(f"Error sending email: {e}")

def send_whatsapp_notification(recipient_phone: str, owner_name: str, customer_name: str, service_name: str, booking_time: datetime, is_owner: bool):
    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        
        message_body = ""
        if is_owner:
            message_body = f"New booking for {owner_name}: {customer_name} booked {service_name} at {booking_time.strftime('%Y-%m-%d %H:%M')}."
        else:
            message_body = f"Hi {customer_name}, your booking for {service_name} with {owner_name} is confirmed for {booking_time.strftime('%Y-%m-%d %H:%M')}."

        message = client.messages.create(
            from_=f'whatsapp:{settings.TWILIO_WHATSAPP_NUMBER}',
            body=message_body,
            to=f'whatsapp:{recipient_phone}'
        )
        print(f"WhatsApp message sent to {recipient_phone}. SID: {message.sid}")
    except Exception as e:
        print(f"Error sending WhatsApp message: {e}")
