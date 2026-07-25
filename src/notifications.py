import os
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from twilio.rest import Client
from .config import settings

def send_email_notification(to_email: str, subject: str, html_content: str):
    message = Mail(
        from_email='noreply@bookslot.app',
        to_emails=to_email,
        subject=subject,
        html_content=html_content
    )
    try:
        sendgrid_client = SendGridAPIClient(settings.SENDGRID_API_KEY)
        response = sendgrid_client.send(message)
        print(f"Email sent to {to_email}. Status Code: {response.status_code}")
        return True
    except Exception as e:
        print(f"Error sending email to {to_email}: {e}")
        return False

def send_whatsapp_notification(to_phone_number: str, message_body: str):
    try:
        twilio_client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        # Twilio requires phone numbers to be E.164 format, e.g., +1234567890
        # For WhatsApp, it's whatsapp:+1234567890
        message = twilio_client.messages.create(
            from_=f'whatsapp:{settings.TWILIO_WHATSAPP_NUMBER}',
            to=f'whatsapp:{to_phone_number}',
            body=message_body
        )
        print(f"WhatsApp message sent to {to_phone_number}. SID: {message.sid}")
        return True
    except Exception as e:
        print(f"Error sending WhatsApp message to {to_phone_number}: {e}")
        return False