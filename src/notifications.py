import os
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from twilio.rest import Client
from .config import settings
from typing import Optional

# SendGrid Email Client
sendgrid_client = SendGridAPIClient(settings.SENDGRID_API_KEY)
FROM_EMAIL = "noreply@bookslot.app"

def send_email(to_email: str, subject: str, html_content: str):
    message = Mail(
        from_email=FROM_EMAIL,
        to_emails=to_email,
        subject=subject,
        html_content=html_content
    )
    try:
        response = sendgrid_client.send(message)
        print(f"Email sent to {to_email}. Status Code: {response.status_code}")
    except Exception as e:
        print(f"Error sending email to {to_email}: {e}")

def send_booking_confirmation_email(customer_email: str, owner_email: str, service_name: str, booking_date, booking_time, owner_name: str):
    subject = f"Booking Confirmation for {service_name} with {owner_name}"
    html_content = f"""
    <html>
    <body>
        <p>Dear Customer,</p>
        <p>Your booking for <b>{service_name}</b> with {owner_name} has been confirmed!</p>
        <p>Date: {booking_date.strftime('%Y-%m-%d')}</p>
        <p>Time: {booking_time.strftime('%H:%M')}</p>
        <p>Thank you for using BookSlot!</p>
    </body>
    </html>
    """
    send_email(customer_email, subject, html_content)

    owner_subject = f"New Booking for {service_name} from {customer_email}"
    owner_html_content = f"""
    <html>
    <body>
        <p>Dear {owner_name},</p>
        <p>You have a new booking for <b>{service_name}</b>.</p>
        <p>Customer Email: {customer_email}</p>
        <p>Date: {booking_date.strftime('%Y-%m-%d')}</p>
        <p>Time: {booking_time.strftime('%H:%M')}</p>
        <p>Please check your dashboard for more details.</p>
    </body>
    </html>
    """
    send_email(owner_email, owner_subject, owner_html_content)


# Twilio SMS Client
twilio_client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)

def send_sms(to_phone_number: str, body: str):
    try:
        message = twilio_client.messages.create(
            to=to_phone_number,
            from_=settings.TWILIO_PHONE_NUMBER,
            body=body
        )
        print(f"SMS sent to {to_phone_number}. SID: {message.sid}")
    except Exception as e:
        print(f"Error sending SMS to {to_phone_number}: {e}")

def send_owner_booking_notification(owner_phone_number: str, service_name: str, booking_date, booking_time, customer_name: str, customer_phone: Optional[str] = None):
    if owner_phone_number:
        body = f"New booking for {service_name} on {booking_date.strftime('%Y-%m-%d')} at {booking_time.strftime('%H:%M')} by {customer_name} (Phone: {customer_phone or 'N/A'})."
        send_sms(owner_phone_number, body)