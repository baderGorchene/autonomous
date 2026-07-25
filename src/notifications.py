import os
import sendgrid
from sendgrid.helpers.mail import Mail, Email, To
from twilio.rest import Client
from .config import settings

def send_email_notification(to_email: str, subject: str, html_content: str):
    try:
        sg = sendgrid.SendGridAPIClient(settings.SENDGRID_API_KEY)
        from_email = Email("no-reply@bookslot.app") # Replace with your verified sender email
        to_email_obj = To(to_email)
        message = Mail(from_email, to_email_obj, subject, html_content=html_content)
        response = sg.send(message)
        # print(f"Email sent to {to_email}. Status Code: {response.status_code}")
        return True
    except Exception as e:
        # print(f"Error sending email to {to_email}: {e}")
        return False

def send_whatsapp_notification(to_phone: str, message_body: str):
    try:
        account_sid = settings.TWILIO_ACCOUNT_SID
        auth_token = settings.TWILIO_AUTH_TOKEN
        twilio_whatsapp_number = settings.TWILIO_WHATSAPP_NUMBER

        client = Client(account_sid, auth_token)
        message = client.messages.create(
            from_=f"whatsapp:{twilio_whatsapp_number}",
            body=message_body,
            to=f"whatsapp:{to_phone}"
        )
        # print(f"WhatsApp message sent to {to_phone}. SID: {message.sid}")
        return True
    except Exception as e:
        # print(f"Error sending WhatsApp message to {to_phone}: {e}")
        return False
