from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from twilio.rest import Client
from .config import settings
import os

def send_email(to_email: str, subject: str, html_content: str):
    try:
        message = Mail(
            from_email='no-reply@bookslot.app', # Replace with your verified sender email
            to_emails=to_email,
            subject=subject,
            html_content=html_content)
        sg = SendGridAPIClient(settings.SENDGRID_API_KEY)
        response = sg.send(message)
        print(f"Email sent to {to_email}. Status Code: {response.status_code}")
        if response.status_code >= 400:
            print(f"Email error: {response.body}")
    except Exception as e:
        print(f"Error sending email to {to_email}: {e}")

def send_whatsapp_message(to_phone_number: str, message_body: str):
    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        message = client.messages.create(
            from_=f'whatsapp:{settings.TWILIO_WHATSAPP_NUMBER}',
            to=f'whatsapp:{to_phone_number}',
            body=message_body
        )
        print(f"WhatsApp message sent to {to_phone_number}. SID: {message.sid}")
    except Exception as e:
        print(f"Error sending WhatsApp message to {to_phone_number}: {e}")
