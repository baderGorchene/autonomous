import os
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from twilio.rest import Client
from .config import settings
from . import schemas
from datetime import datetime

# Initialize SendGrid
sendgrid_client = SendGridAPIClient(settings.SENDGRID_API_KEY)

# Initialize Twilio
twilio_client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
twilio_whatsapp_number = settings.TWILIO_WHATSAPP_NUMBER

def send_booking_confirmation_email(owner_email: str, customer_email: str, booking_details: schemas.Booking, service_name: str, owner_name: str):
    # Email to customer
    customer_subject = f"Your booking for {service_name} at {owner_name} is confirmed!"
    customer_html_content = f"""
    <html>
    <body>
        <p>Hi {booking_details.customer_name},</p>
        <p>Your booking for <b>{service_name}</b> with <b>{owner_name}</b> has been confirmed.</p>
        <p><b>Date & Time:</b> {booking_details.booking_time.strftime('%Y-%m-%d %H:%M')}</p>
        <p>We look forward to seeing you!</p>
        <p>Best regards,<br>The BookSlot Team</p>
    </body>
    </html>
    """
    message_to_customer = Mail(
        from_email='no-reply@bookslot.app',
        to_emails=customer_email,
        subject=customer_subject,
        html_content=customer_html_content
    )
    try:
        if settings.SENDGRID_API_KEY:
            response = sendgrid_client.send(message_to_customer)
            print(f"Customer Email sent. Status Code: {response.status_code}")
        else:
            print("SendGrid API key not set. Skipping customer email notification.")
    except Exception as e:
        print(f"Error sending customer email: {e}")

    # Email to owner
    owner_subject = f"New Booking: {service_name} by {booking_details.customer_name}"
    owner_html_content = f"""
    <html>
    <body>
        <p>Hi {owner_name},</p>
        <p>You have a new booking!</p>
        <p><b>Service:</b> {service_name}</p>
        <p><b>Date & Time:</b> {booking_details.booking_time.strftime('%Y-%m-%d %H:%M')}</p>
        <p><b>Customer Name:</b> {booking_details.customer_name}</p>
        <p><b>Customer Email:</b> {booking_details.customer_email}</p>
        <p><b>Customer Phone:</b> {booking_details.customer_phone}</p>
        <p>Manage your bookings on your BookSlot dashboard.</p>
        <p>Best regards,<br>The BookSlot Team</p>
    </body>
    </html>
    """
    message_to_owner = Mail(
        from_email='no-reply@bookslot.app',
        to_emails=owner_email,
        subject=owner_subject,
        html_content=owner_html_content
    )
    try:
        if settings.SENDGRID_API_KEY:
            response = sendgrid_client.send(message_to_owner)
            print(f"Owner Email sent. Status Code: {response.status_code}")
        else:
            print("SendGrid API key not set. Skipping owner email notification.")
    except Exception as e:
        print(f"Error sending owner email: {e}")

def send_whatsapp_notification(to_phone_number: str, message: str):
    try:
        if settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN and settings.TWILIO_WHATSAPP_NUMBER:
            message = twilio_client.messages.create(
                from_=twilio_whatsapp_number,
                body=message,
                to=f'whatsapp:{to_phone_number}'
            )
            print(f"WhatsApp message sent. SID: {message.sid}")
        else:
            print("Twilio credentials not fully set. Skipping WhatsApp notification.")
    except Exception as e:
        print(f"Error sending WhatsApp message: {e}")
