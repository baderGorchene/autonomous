import os
import sendgrid
from sendgrid.helpers.mail import Mail, Email, To
from twilio.rest import Client
from .config import settings

def send_email_notification(recipient_email: str, subject: str, body_html: str):
    if not settings.SENDGRID_API_KEY:
        print(f"SendGrid API Key not set. Skipping email to {recipient_email}. Subject: {subject}")
        return

    try:
        sg = sendgrid.SendGridAPIClient(settings.SENDGRID_API_KEY)
        from_email = Email("no-reply@bookslot.app") # Replace with your verified sender email
        to_email = To(recipient_email)
        message = Mail(from_email, to_email, subject, html_content=body_html)
        response = sg.send(message)
        print(f"Email sent to {recipient_email}. Status Code: {response.status_code}")
    except Exception as e:
        print(f"Error sending email to {recipient_email}: {e}")

def send_whatsapp_notification(to_number: str, message: str):
    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN or not settings.TWILIO_WHATSAPP_NUMBER:
        print(f"Twilio credentials not fully set. Skipping WhatsApp message to {to_number}.")
        return

    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        message = client.messages.create(
            from_=settings.TWILIO_WHATSAPP_NUMBER,
            body=message,
            to=f"whatsapp:{to_number}"
        )
        print(f"WhatsApp message sent to {to_number}. SID: {message.sid}")
    except Exception as e:
        print(f"Error sending WhatsApp message to {to_number}: {e}")
