from .config import settings
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

def send_email(to_email: str, subject: str, body: str):
    # This would integrate with SendGrid or a similar service
    # For now, just log the email content
    logger.info(f"Sending email to {to_email}: Subject: {subject}, Body: {body}")
    # Example using SendGrid (requires sendgrid library and API key)
    # from sendgrid import SendGridAPIClient
    # from sendgrid.helpers.mail import Mail
    # message = Mail(from_email='noreply@bookslot.app', to_emails=to_email, subject=subject, html_content=body)
    # try:
    #     sg = SendGridAPIClient(settings.SENDGRID_API_KEY)
    #     response = sg.send(message)
    #     logger.info(f"Email sent via SendGrid. Status Code: {response.status_code}")
    # except Exception as e:
    #     logger.error(f"Error sending email via SendGrid: {e}")

def send_whatsapp_message(to_phone: str, body: str):
    # This would integrate with Twilio WhatsApp API
    # For now, just log the message content
    logger.info(f"Sending WhatsApp message to {to_phone}: Body: {body}")
    # Example using Twilio (requires twilio library and credentials)
    # from twilio.rest import Client
    # client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
    # try:
    #     message = client.messages.create(
    #         from_=f'whatsapp:{settings.TWILIO_WHATSAPP_NUMBER}',
    #         body=body,
    #         to=f'whatsapp:{to_phone}'
    #     )
    #     logger.info(f"WhatsApp message sent via Twilio. SID: {message.sid}")
    # except Exception as e:
    #     logger.error(f"Error sending WhatsApp message via Twilio: {e}")

def send_booking_confirmation_email(customer_email: str, customer_name: str, service_name: str, booking_time: datetime, owner_name: str, business_name: str):
    subject = f"Your Booking Confirmation with {business_name}"
    body = f"""
    Hello {customer_name},
    <br><br>
    Your booking for {service_name} with {business_name} (managed by {owner_name}) has been confirmed!
    <br>
    Date and Time: {booking_time.strftime('%Y-%m-%d %H:%M')}
    <br><br>
    We look forward to seeing you.
    <br><br>
    Best regards,<br>
    The {business_name} Team
    """
    send_email(customer_email, subject, body)

def send_owner_notification(owner_email: str, owner_phone: str, customer_name: str, customer_email: str, customer_phone: str, service_name: str, booking_time: datetime):
    subject = f"New Booking for {service_name}!"
    email_body = f"""
    Hello {owner_email},
    <br><br>
    You have a new booking!
    <br>
    Service: {service_name}
    <br>
    Date and Time: {booking_time.strftime('%Y-%m-%d %H:%M')}
    <br>
    Customer Name: {customer_name}
    <br>
    Customer Email: {customer_email}
    <br>
    Customer Phone: {customer_phone or 'N/A'}
    <br><br>
    BookSlot App
    """
    send_email(owner_email, subject, email_body)

    whatsapp_body = f"New booking for {service_name} at {booking_time.strftime('%Y-%m-%d %H:%M')}. Customer: {customer_name} ({customer_phone or customer_email})"
    if owner_phone:
        send_whatsapp_message(owner_phone, whatsapp_body)
