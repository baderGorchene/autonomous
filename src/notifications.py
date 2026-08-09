from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from twilio.rest import Client
from typing import Dict, Any
from .config import settings

# Email via SendGrid
def send_email(to_email: str, subject: str, html_content: str):
    if not settings.SENDGRID_API_KEY or settings.SENDGRID_API_KEY == "SG....":
        print(f"Skipping email to {to_email}: SendGrid API key not configured.")
        print(f"Subject: {subject}\nContent: {html_content}")
        return

    message = Mail(
        from_email='no-reply@bookslot.app', # Replace with your verified sender
        to_emails=to_email,
        subject=subject,
        html_content=html_content
    )
    try:
        sendgrid_client = SendGridAPIClient(settings.SENDGRID_API_KEY)
        response = sendgrid_client.send(message)
        print(f"Email sent to {to_email}, Status Code: {response.status_code}")
    except Exception as e:
        print(f"Error sending email to {to_email}: {e}")

# WhatsApp via Twilio
def send_whatsapp_message(to_phone_number: str, message_body: str):
    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN or not settings.TWILIO_PHONE_NUMBER:
        print(f"Skipping WhatsApp to {to_phone_number}: Twilio credentials not configured.")
        print(f"Message: {message_body}")
        return

    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        message = client.messages.create(
            from_=f'whatsapp:{settings.TWILIO_PHONE_NUMBER}',
            body=message_body,
            to=f'whatsapp:{to_phone_number}'
        )
        print(f"WhatsApp message sent to {to_phone_number}, SID: {message.sid}")
    except Exception as e:
        print(f"Error sending WhatsApp message to {to_phone_number}: {e}")

def send_booking_confirmation_email(
    owner_email: str,
    customer_email: str,
    booking_details: Dict[str, Any],
    is_owner_notification: bool
):
    service_name = booking_details['service_name']
    booking_date = booking_details['date'].strftime('%Y-%m-%d')
    booking_time = booking_details['time'].strftime('%H:%M')
    customer_name = booking_details['customer_name']
    owner_name = booking_details['owner_name']

    if is_owner_notification:
        subject = f"New Booking for {service_name} on {booking_date} at {booking_time}"
        html_content = f"""
            <p>Dear {owner_name},</p>
            <p>You have a new booking!</p>
            <p>Service: {service_name}</p>
            <p>Date: {booking_date}</p>
            <p>Time: {booking_time}</p>
            <p>Customer: {customer_name}</p>
            <p>Customer Email: {customer_email}</p>
            <p>Customer Phone: {booking_details.get('customer_phone', 'N/A')}</p>
            <p>Thank you!</p>
        """
        send_email(owner_email, subject, html_content)
    else:
        subject = f"Your Booking Confirmation for {service_name} on {booking_date} at {booking_time}"
        html_content = f"""
            <p>Dear {customer_name},</p>
            <p>Your booking for {service_name} with {owner_name} is confirmed!</p>
            <p>Date: {booking_date}</p>
            <p>Time: {booking_time}</p>
            <p>We look forward to seeing you.</p>
        """
        send_email(customer_email, subject, html_content)

def send_booking_confirmation_whatsapp(
    owner_phone: str,
    customer_phone: str,
    booking_details: Dict[str, Any],
    is_owner_notification: bool
):
    service_name = booking_details['service_name']
    booking_date = booking_details['date'].strftime('%Y-%m-%d')
    booking_time = booking_details['time'].strftime('%H:%M')
    customer_name = booking_details['customer_name']
    owner_name = booking_details['owner_name']

    if is_owner_notification:
        message_body = (
            f"New booking for {service_name} on {booking_date} at {booking_time}. "
            f"Customer: {customer_name}, Phone: {customer_phone}"
        )
        send_whatsapp_message(owner_phone, message_body)
    else:
        message_body = (
            f"Hi {customer_name}, your booking for {service_name} with {owner_name} "
            f"on {booking_date} at {booking_time} is confirmed!"
        )
        send_whatsapp_message(customer_phone, message_body)
