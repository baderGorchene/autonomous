import os
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from twilio.rest import Client
from .config import settings

def send_email_notification(recipient_email: str, subject: str, body: str):
    try:
        message = Mail(
            from_email='no-reply@bookslot.app', # Replace with your verified sender email
            to_emails=recipient_email,
            subject=subject,
            html_content=body
        )
        sg = SendGridAPIClient(settings.SENDGRID_API_KEY)
        response = sg.send(message)
        print(f"Email sent to {recipient_email}. Status Code: {response.status_code}")
        return True
    except Exception as e:
        print(f"Error sending email to {recipient_email}: {e}")
        return False

def send_whatsapp_notification(recipient_phone: str, message: str):
    try:
        # Twilio requires phone numbers in E.164 format, e.g., +12345678900
        # Ensure recipient_phone is correctly formatted before calling this function
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        
        # Twilio WhatsApp numbers are typically prefixed with 'whatsapp:'
        message = client.messages.create(
            from_=f'whatsapp:{settings.TWILIO_WHATSAPP_NUMBER}',
            body=message,
            to=f'whatsapp:{recipient_phone}'
        )
        print(f"WhatsApp message sent to {recipient_phone}. SID: {message.sid}")
        return True
    except Exception as e:
        print(f"Error sending WhatsApp message to {recipient_phone}: {e}")
        return False
